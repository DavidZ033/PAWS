import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { ApiError } from '../api/client';
import type { Schedule } from '../api/types';
import { Button, Card } from '../components/ui';
import { useRobot } from '../state/RobotContext';
import { colors, DAY_LABELS, formatDays } from '../theme';

const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;

export function ScheduleScreen() {
  const { client, connection } = useRobot();
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [time, setTime] = useState('08:00');
  const [portions, setPortions] = useState(1);
  const [days, setDays] = useState<number[]>([]);
  const [label, setLabel] = useState('');

  const load = useCallback(async () => {
    if (!client) return;
    setLoading(true);
    try {
      setSchedule(await client.schedule());
      setError('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load the schedule');
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    if (connection === 'connected') load();
  }, [connection, load]);

  // Run a change on the robot, then reload so the list matches it exactly.
  const change = async (action: () => Promise<unknown>) => {
    try {
      await action();
      setError('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Change failed');
    }
    await load();
  };

  const add = () => {
    if (!TIME_PATTERN.test(time)) {
      setError('Enter the time as 24-hour HH:MM, for example 07:30');
      return;
    }
    change(() => client!.addSchedule({ time, portions, days, label: label.trim(), enabled: true }));
    setLabel('');
  };

  const toggleDay = (day: number) =>
    setDays((current) => (current.includes(day) ? current.filter((d) => d !== day) : [...current, day].sort()));

  if (!client) return <Text style={styles.empty}>Enter the robot's address on the Settings tab first.</Text>;

  return (
    <ScrollView
      contentContainerStyle={styles.screen}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={colors.muted} />}
    >
      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Text style={styles.heading}>Feeding times</Text>
      {schedule?.next ? (
        <Text style={styles.muted}>
          Next: {schedule.next.at.replace('T', ' ').slice(0, 16)} ({schedule.next.portions} portion
          {schedule.next.portions === 1 ? '' : 's'})
        </Text>
      ) : null}
      {schedule && schedule.entries.length === 0 ? <Text style={styles.muted}>Nothing scheduled yet.</Text> : null}

      {schedule?.entries.map((entry) => (
        <Card key={entry.id} style={styles.entry}>
          <View style={styles.entryText}>
            <Text style={styles.time}>{entry.time}</Text>
            <Text style={styles.muted}>
              {formatDays(entry.days)}, {entry.portions} portion{entry.portions === 1 ? '' : 's'}
              {entry.label ? `, ${entry.label}` : ''}
            </Text>
          </View>
          <Switch
            value={entry.enabled}
            onValueChange={(enabled) => change(() => client.updateSchedule(entry.id, { enabled }))}
          />
          <Button title="Delete" color={colors.danger} onPress={() => change(() => client.removeSchedule(entry.id))} style={styles.small} />
        </Card>
      ))}

      <Text style={styles.heading}>Add a feeding</Text>
      <Card style={styles.form}>
        <View style={styles.formRow}>
          <Text style={styles.muted}>Time (24h)</Text>
          <TextInput
            value={time}
            onChangeText={setTime}
            placeholder="HH:MM"
            placeholderTextColor={colors.muted}
            keyboardType="numbers-and-punctuation"
            maxLength={5}
            style={styles.input}
          />
        </View>
        <View style={styles.formRow}>
          <Text style={styles.muted}>Portions</Text>
          <View style={styles.stepper}>
            <Button title="-" color={colors.border} onPress={() => setPortions((p) => Math.max(1, p - 1))} style={styles.small} />
            <Text style={styles.time}>{portions}</Text>
            <Button title="+" color={colors.border} onPress={() => setPortions((p) => Math.min(5, p + 1))} style={styles.small} />
          </View>
        </View>
        <Text style={styles.muted}>Days (none selected = every day)</Text>
        <View style={styles.days}>
          {DAY_LABELS.map((name, day) => (
            <Pressable key={name} onPress={() => toggleDay(day)} style={[styles.day, days.includes(day) && styles.dayOn]}>
              <Text style={styles.dayText}>{name}</Text>
            </Pressable>
          ))}
        </View>
        <TextInput
          value={label}
          onChangeText={setLabel}
          placeholder="Label (optional), for example Breakfast"
          placeholderTextColor={colors.muted}
          style={styles.input}
        />
        <Button title="Add to schedule" onPress={add} disabled={connection !== 'connected'} />
      </Card>
      <Text style={styles.muted}>Times follow the clock on the robot's Raspberry Pi.</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { padding: 12, gap: 10 },
  heading: { color: colors.text, fontSize: 18, fontWeight: '700', marginTop: 6 },
  muted: { color: colors.muted, fontSize: 13 },
  empty: { color: colors.muted, padding: 24, textAlign: 'center' },
  error: { color: colors.danger },
  entry: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  entryText: { flex: 1 },
  time: { color: colors.text, fontSize: 20, fontWeight: '700', minWidth: 24, textAlign: 'center' },
  small: { paddingVertical: 8, paddingHorizontal: 12 },
  form: { gap: 12 },
  formRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  input: {
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    minWidth: 90,
    fontSize: 16,
  },
  days: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  day: { paddingVertical: 8, paddingHorizontal: 10, borderRadius: 8, borderWidth: 1, borderColor: colors.border },
  dayOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  dayText: { color: colors.text, fontSize: 13 },
});
