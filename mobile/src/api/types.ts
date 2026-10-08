// Shapes of the JSON the robot sends and accepts.
// These mirror paws/server.py and paws/robot.py on the Pi.

export interface Pose {
  x: number;
  y: number;
  theta: number;
  theta_deg: number;
}

export interface Waypoint {
  x: number;
  y: number;
  /** Heading in radians. Leave out to keep the current heading. */
  theta?: number | null;
}

export interface NavigationStatus {
  state: 'idle' | 'running' | 'reached' | 'timeout' | 'cancelled';
  active: boolean;
  target: Waypoint | null;
  waypoint_index: number | null;
  waypoint_count: number;
  distance_to_target: number | null;
}

export interface NextFeeding {
  at: string;
  id: string;
  portions: number;
  label: string;
}

export interface RobotStatus {
  name: string;
  version: string;
  simulated: boolean;
  time: number;
  uptime: number;
  mode: 'manual' | 'auto';
  drive: { vx: number; vy: number; omega: number; wheels: Record<string, number> };
  pose: Pose;
  encoders: { enc1: number; enc2: number };
  navigation: NavigationStatus;
  launcher: { running: boolean; power: number; last_launch: number | null };
  feeder: { busy: boolean; last_fed: number | null; total_portions: number; mode: string };
  next_feeding: NextFeeding | null;
  camera: { available: boolean; backend: string; width: number; height: number; fps: number; error: string | null };
  detection: {
    enabled: boolean;
    available: boolean;
    reason: string | null;
    dog_present: boolean;
    confidence: number | null;
    box: [number, number, number, number] | null;
    last_seen: number | null;
  };
  last_event_id: number;
}

export interface RobotEvent {
  id: number;
  /** Unix time in seconds. */
  time: number;
  type: string;
  message: string;
  data: Record<string, unknown>;
  snapshot: string | null;
}

export interface ScheduleEntry {
  id: string;
  /** 24-hour "HH:MM" in the robot's local time. */
  time: string;
  /** 0 = Monday .. 6 = Sunday. Empty means every day. */
  days: number[];
  portions: number;
  label: string;
  enabled: boolean;
}

export type NewScheduleEntry = Omit<ScheduleEntry, 'id'>;

export interface Schedule {
  entries: ScheduleEntry[];
  next: NextFeeding | null;
}

/** Where to find the robot. Saved on the phone. */
export interface ConnectionSettings {
  host: string;
  port: number;
  token: string;
}

/** Messages the app sends over the WebSocket. */
export type OutgoingMessage =
  | { type: 'drive'; vx: number; vy: number; omega: number }
  | { type: 'stop' }
  | { type: 'feed'; portions: number }
  | { type: 'launch'; power?: number; duration?: number }
  | { type: 'launcher_stop' }
  | { type: 'ping' };

/** Messages the robot pushes over the WebSocket. */
export type IncomingMessage =
  | { type: 'status'; data: RobotStatus }
  | { type: 'event'; data: RobotEvent }
  | { type: 'ack'; action: string; ok: boolean }
  | { type: 'pong' }
  | { type: 'error'; message: string };
