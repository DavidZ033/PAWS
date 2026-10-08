// REST client for the PAWS robot.
//
// Use this for one-off actions and queries (feed now, edit the schedule,
// load the event history). Live driving goes through PawsSocket instead,
// because a WebSocket has far less delay per command.

import type {
  ConnectionSettings,
  NewScheduleEntry,
  Pose,
  RobotEvent,
  RobotStatus,
  Schedule,
  ScheduleEntry,
  Waypoint,
} from './types';

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
    this.name = 'ApiError';
  }
}

export function baseUrl(settings: ConnectionSettings): string {
  return `http://${settings.host.trim()}:${settings.port}`;
}

export class PawsClient {
  readonly base: string;
  private token: string;
  private timeoutMs: number;

  constructor(settings: ConnectionSettings, timeoutMs = 5000) {
    this.base = baseUrl(settings);
    this.token = settings.token;
    this.timeoutMs = timeoutMs;
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let response: Response;
    try {
      response = await fetch(this.base + path, {
        method,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(this.token ? { 'X-PAWS-Token': this.token } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(`Cannot reach the robot at ${this.base}. Check the address and that you are on the same WiFi.`);
    } finally {
      clearTimeout(timer);
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status})`;
      throw new ApiError(detail, response.status);
    }
    return data as T;
  }

  /** Adds the token to URLs that are loaded by an image or web view. */
  private withToken(url: string): string {
    if (!this.token) return url;
    return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(this.token)}`;
  }

  // ---- status ----

  status(): Promise<RobotStatus> {
    return this.request('GET', '/api/status');
  }

  // ---- driving ----

  /** Each value is -1..1. Must be re-sent a few times a second or the robot stops. */
  drive(vx: number, vy: number, omega: number): Promise<{ ok: boolean }> {
    return this.request('POST', '/api/drive', { vx, vy, omega });
  }

  /** Emergency stop: wheels, launcher and navigation. */
  stop(): Promise<{ ok: boolean }> {
    return this.request('POST', '/api/stop', {});
  }

  // ---- launcher and feeder ----

  launch(power?: number, duration?: number): Promise<{ ok: boolean; power: number; duration: number }> {
    return this.request('POST', '/api/launcher/launch', { power, duration });
  }

  stopLauncher(): Promise<{ ok: boolean }> {
    return this.request('POST', '/api/launcher/stop', {});
  }

  feed(portions = 1): Promise<{ ok: boolean; portions: number }> {
    return this.request('POST', '/api/feeder/dispense', { portions });
  }

  // ---- feeding schedule ----

  schedule(): Promise<Schedule> {
    return this.request('GET', '/api/schedule');
  }

  addSchedule(entry: NewScheduleEntry): Promise<ScheduleEntry> {
    return this.request('POST', '/api/schedule', entry);
  }

  updateSchedule(id: string, changes: Partial<NewScheduleEntry>): Promise<ScheduleEntry> {
    return this.request('PATCH', `/api/schedule/${id}`, changes);
  }

  removeSchedule(id: string): Promise<{ ok: boolean }> {
    return this.request('DELETE', `/api/schedule/${id}`);
  }

  // ---- navigation ----

  goto(target: Waypoint): Promise<{ ok: boolean }> {
    return this.request('POST', '/api/nav/goto', target);
  }

  /** loops = 0 repeats until cancelled. */
  patrol(waypoints: Waypoint[], loops = 1): Promise<{ ok: boolean }> {
    return this.request('POST', '/api/nav/patrol', { waypoints, loops });
  }

  cancelNavigation(): Promise<{ ok: boolean }> {
    return this.request('POST', '/api/nav/cancel', {});
  }

  /** Tell the robot that where it is sitting now is the origin (or the given pose). */
  resetPose(pose: Partial<Pick<Pose, 'x' | 'y' | 'theta'>> = {}): Promise<{ ok: boolean; pose: Pose }> {
    return this.request('POST', '/api/odometry/reset', pose);
  }

  // ---- events ----

  async events(limit = 50, since = 0): Promise<RobotEvent[]> {
    const data = await this.request<{ events: RobotEvent[] }>('GET', `/api/events?limit=${limit}&since=${since}`);
    return data.events;
  }

  eventSnapshotUrl(eventId: number): string {
    return this.withToken(`${this.base}/api/events/${eventId}/snapshot`);
  }

  // ---- camera and detection ----

  /** MJPEG stream. Load it in a web view or an <img> tag. */
  streamUrl(): string {
    return this.withToken(`${this.base}/api/camera/stream`);
  }

  snapshotUrl(): string {
    return this.withToken(`${this.base}/api/camera/snapshot?t=${Date.now()}`);
  }

  setDetection(enabled: boolean): Promise<RobotStatus['detection']> {
    return this.request('POST', '/api/detection', { enabled });
  }
}
