import { StatusBar } from 'expo-status-bar';
import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { ControlScreen } from './src/screens/ControlScreen';
import { EventsScreen } from './src/screens/EventsScreen';
import { ScheduleScreen } from './src/screens/ScheduleScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { RobotProvider, useRobot } from './src/state/RobotContext';
import { colors } from './src/theme';

const TABS = ['Control', 'Schedule', 'Events', 'Settings'] as const;
type Tab = (typeof TABS)[number];

function Shell() {
  const { ready, settings, connection, status, socket } = useRobot();
  const [tab, setTab] = useState<Tab>('Control');

  // First launch: there is no robot address yet, so start on Settings.
  useEffect(() => {
    if (ready && !settings.host) setTab('Settings');
  }, [ready, settings.host]);

  // Leaving the Control tab removes the joysticks, so make sure the robot
  // is not left with a drive command still active.
  useEffect(() => {
    if (tab !== 'Control') socket?.setDrive({ vx: 0, vy: 0, omega: 0 });
  }, [tab, socket]);

  const dot = connection === 'connected' ? colors.good : connection === 'connecting' ? colors.warn : colors.danger;

  return (
    <SafeAreaView style={styles.app}>
      <StatusBar style="light" />
      <View style={styles.header}>
        <Text style={styles.title}>{status?.name ?? 'PAWS'}</Text>
        <View style={[styles.dot, { backgroundColor: dot }]} />
        <Text style={styles.connection}>{connection}</Text>
      </View>

      <View style={styles.content}>
        {tab === 'Control' ? <ControlScreen /> : null}
        {tab === 'Schedule' ? <ScheduleScreen /> : null}
        {tab === 'Events' ? <EventsScreen /> : null}
        {tab === 'Settings' ? <SettingsScreen /> : null}
      </View>

      <View style={styles.tabs}>
        {TABS.map((name) => (
          <Pressable key={name} style={styles.tab} onPress={() => setTab(name)}>
            <Text style={[styles.tabText, tab === name && styles.tabActive]}>{name}</Text>
          </Pressable>
        ))}
      </View>
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <RobotProvider>
        <Shell />
      </RobotProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 10 },
  title: { color: colors.text, fontSize: 20, fontWeight: '800', flex: 1 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  connection: { color: colors.muted, fontSize: 13 },
  content: { flex: 1 },
  tabs: { flexDirection: 'row', borderTopWidth: 1, borderTopColor: colors.border },
  tab: { flex: 1, paddingVertical: 14, alignItems: 'center' },
  tabText: { color: colors.muted, fontSize: 14 },
  tabActive: { color: colors.primary, fontWeight: '700' },
});
