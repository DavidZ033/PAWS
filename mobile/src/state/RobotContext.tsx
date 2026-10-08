// Shared app state: where the robot is, the live connection to it, its
// latest status and the recent events. Every screen reads from here.

import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { PawsClient } from '../api/client';
import { ConnectionState, PawsSocket, socketUrl } from '../api/socket';
import type { ConnectionSettings, RobotEvent, RobotStatus } from '../api/types';

const STORAGE_KEY = 'paws.connection';
const MAX_EVENTS = 200;

export const DEFAULT_SETTINGS: ConnectionSettings = { host: '', port: 8000, token: '' };

interface RobotContextValue {
  /** False until saved settings have been read from the phone. */
  ready: boolean;
  settings: ConnectionSettings;
  saveSettings: (settings: ConnectionSettings) => Promise<void>;
  /** Null until a robot address has been entered. */
  client: PawsClient | null;
  socket: PawsSocket | null;
  connection: ConnectionState;
  status: RobotStatus | null;
  /** Newest first. */
  events: RobotEvent[];
  refreshEvents: () => Promise<void>;
}

const RobotContext = createContext<RobotContextValue | null>(null);

function mergeEvents(current: RobotEvent[], incoming: RobotEvent[]): RobotEvent[] {
  const byId = new Map<number, RobotEvent>();
  for (const event of [...current, ...incoming]) byId.set(event.id, event);
  return [...byId.values()].sort((a, b) => b.id - a.id).slice(0, MAX_EVENTS);
}

export function RobotProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [settings, setSettings] = useState<ConnectionSettings>(DEFAULT_SETTINGS);
  const [connection, setConnection] = useState<ConnectionState>('disconnected');
  const [status, setStatus] = useState<RobotStatus | null>(null);
  const [events, setEvents] = useState<RobotEvent[]>([]);
  const socketRef = useRef<PawsSocket | null>(null);
  const [socket, setSocket] = useState<PawsSocket | null>(null);

  // Load the saved robot address once at startup.
  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((raw) => {
        if (raw) setSettings({ ...DEFAULT_SETTINGS, ...JSON.parse(raw) });
      })
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);

  const saveSettings = useCallback(async (next: ConnectionSettings) => {
    const cleaned = { ...next, host: next.host.trim() };
    setSettings(cleaned);
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(cleaned)).catch(() => {});
  }, []);

  const client = useMemo(() => (settings.host ? new PawsClient(settings) : null), [settings]);

  const refreshEvents = useCallback(async () => {
    if (!client) return;
    const recent = await client.events(100);
    setEvents((current) => mergeEvents(current, recent));
  }, [client]);

  // Open (or re-open) the live connection whenever the address changes.
  useEffect(() => {
    socketRef.current?.close();
    socketRef.current = null;
    setSocket(null);
    setStatus(null);
    setEvents([]);
    if (!ready || !settings.host) return;

    const live = new PawsSocket(socketUrl(settings), {
      onStatus: setStatus,
      onEvent: (event) => setEvents((current) => mergeEvents(current, [event])),
      onState: (state) => {
        setConnection(state);
        if (state === 'disconnected') setStatus(null);
      },
    });
    socketRef.current = live;
    setSocket(live);
    live.connect();
    return () => live.close();
  }, [ready, settings]);

  // Fetch the event history each time we (re)connect.
  useEffect(() => {
    if (connection === 'connected') refreshEvents().catch(() => {});
  }, [connection, refreshEvents]);

  const value = useMemo<RobotContextValue>(
    () => ({ ready, settings, saveSettings, client, socket, connection, status, events, refreshEvents }),
    [ready, settings, saveSettings, client, socket, connection, status, events, refreshEvents],
  );

  return <RobotContext.Provider value={value}>{children}</RobotContext.Provider>;
}

export function useRobot(): RobotContextValue {
  const value = useContext(RobotContext);
  if (!value) throw new Error('useRobot must be used inside <RobotProvider>');
  return value;
}
