// Live connection to the robot.
//
// The robot pushes its full status five times a second plus every new
// event, and accepts drive commands with very little delay.
//
// Two safety details worth knowing:
//   1. While a joystick is held, the current drive command is re-sent ten
//      times a second. The robot stops by itself if those stop arriving,
//      so a dropped connection never leaves it driving.
//   2. If the connection drops, this class reconnects on its own, waiting
//      a little longer after each failed attempt.

import type { ConnectionSettings, IncomingMessage, OutgoingMessage, RobotEvent, RobotStatus } from './types';

export type ConnectionState = 'disconnected' | 'connecting' | 'connected';

export interface SocketHandlers {
  onStatus?: (status: RobotStatus) => void;
  onEvent?: (event: RobotEvent) => void;
  onState?: (state: ConnectionState) => void;
  onError?: (message: string) => void;
}

const DRIVE_INTERVAL_MS = 100;
const MAX_RETRY_MS = 5000;

export function socketUrl(settings: ConnectionSettings): string {
  const token = settings.token ? `?token=${encodeURIComponent(settings.token)}` : '';
  return `ws://${settings.host.trim()}:${settings.port}/ws${token}`;
}

export class PawsSocket {
  private ws: WebSocket | null = null;
  private wanted = false;
  private retryMs = 1000;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private driveTimer: ReturnType<typeof setInterval> | null = null;
  private command = { vx: 0, vy: 0, omega: 0 };
  private state: ConnectionState = 'disconnected';

  constructor(private url: string, private handlers: SocketHandlers = {}) {}

  get connected(): boolean {
    return this.state === 'connected';
  }

  connect(): void {
    this.wanted = true;
    this.open();
  }

  /** Close for good. No more reconnect attempts. */
  close(): void {
    this.wanted = false;
    this.stopDriveLoop();
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.ws?.close();
    this.ws = null;
    this.setState('disconnected');
  }

  private setState(state: ConnectionState): void {
    if (state !== this.state) {
      this.state = state;
      this.handlers.onState?.(state);
    }
  }

  private open(): void {
    if (!this.wanted || this.ws) return;
    this.setState('connecting');
    const ws = new WebSocket(this.url);
    this.ws = ws;

    ws.onopen = () => {
      this.retryMs = 1000;
      this.setState('connected');
    };

    ws.onmessage = (message) => {
      let parsed: IncomingMessage;
      try {
        parsed = JSON.parse(String(message.data));
      } catch {
        return;
      }
      if (parsed.type === 'status') this.handlers.onStatus?.(parsed.data);
      else if (parsed.type === 'event') this.handlers.onEvent?.(parsed.data);
      else if (parsed.type === 'error') this.handlers.onError?.(parsed.message);
    };

    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.stopDriveLoop();
      this.command = { vx: 0, vy: 0, omega: 0 };
      this.setState('disconnected');
      if (this.wanted) {
        this.retryTimer = setTimeout(() => this.open(), this.retryMs);
        this.retryMs = Math.min(MAX_RETRY_MS, this.retryMs * 1.5);
      }
    };

    // An error is always followed by a close, which handles the retry.
    ws.onerror = () => {};
  }

  send(message: OutgoingMessage): boolean {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
      return true;
    }
    return false;
  }

  // ---- driving ----

  /**
   * Set the drive command. Each value is -1..1:
   *   vx     forward (+) / backward (-)
   *   vy     left (+) / right (-)
   *   omega  counter-clockwise (+) / clockwise (-)
   * Call it as often as you like; it is sent to the robot at a steady rate.
   * Pass only the parts you want to change.
   */
  setDrive(part: Partial<{ vx: number; vy: number; omega: number }>): void {
    this.command = { ...this.command, ...part };
    const moving = this.command.vx !== 0 || this.command.vy !== 0 || this.command.omega !== 0;
    if (moving && !this.driveTimer) {
      this.sendDrive();
      this.driveTimer = setInterval(() => this.sendDrive(), DRIVE_INTERVAL_MS);
    } else if (!moving && this.driveTimer) {
      this.stopDriveLoop();
      this.sendDrive(); // one explicit zero so the robot stops right away
    }
  }

  private sendDrive(): void {
    this.send({ type: 'drive', ...this.command });
  }

  private stopDriveLoop(): void {
    if (this.driveTimer) clearInterval(this.driveTimer);
    this.driveTimer = null;
  }

  // ---- actions ----

  /** Emergency stop: wheels, launcher and navigation. */
  stop(): boolean {
    this.stopDriveLoop();
    this.command = { vx: 0, vy: 0, omega: 0 };
    return this.send({ type: 'stop' });
  }

  feed(portions = 1): boolean {
    return this.send({ type: 'feed', portions });
  }

  launch(power?: number, duration?: number): boolean {
    return this.send({ type: 'launch', power, duration });
  }
}
