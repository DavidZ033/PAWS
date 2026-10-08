import React, { useState } from 'react';
import { FlatList, Image, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import type { RobotEvent } from '../api/types';
import { useRobot } from '../state/RobotContext';
import { colors } from '../theme';

const TYPE_COLORS: Record<string, string> = {
  dog_detected: colors.good,
  feed: colors.primary,
  feed_skipped: colors.danger,
  launch: colors.warn,
};

function formatTime(unixSeconds: number): string {
  const date = new Date(unixSeconds * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getMonth() + 1}/${date.getDate()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function EventsScreen() {
  const { client, events, refreshEvents } = useRobot();
  const [refreshing, setRefreshing] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  const refresh = async () => {
    setRefreshing(true);
    await refreshEvents().catch(() => {});
    setRefreshing(false);
  };

  const renderItem = ({ item }: { item: RobotEvent }) => (
    <Pressable
      style={styles.item}
      onPress={() => setOpen(open === item.id ? null : item.id)}
      disabled={!item.snapshot}
    >
      <View style={[styles.dot, { backgroundColor: TYPE_COLORS[item.type] ?? colors.muted }]} />
      <View style={styles.body}>
        <Text style={styles.message}>{item.message}</Text>
        <Text style={styles.meta}>
          {formatTime(item.time)}
          {item.snapshot ? (open === item.id ? '   hide photo' : '   tap for photo') : ''}
        </Text>
        {open === item.id && item.snapshot && client ? (
          <Image source={{ uri: client.eventSnapshotUrl(item.id) }} style={styles.photo} resizeMode="contain" />
        ) : null}
      </View>
    </Pressable>
  );

  return (
    <FlatList
      data={events}
      keyExtractor={(item) => String(item.id)}
      renderItem={renderItem}
      contentContainerStyle={styles.list}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.muted} />}
      ListEmptyComponent={<Text style={styles.empty}>No events yet. Feedings, launches and dog sightings show up here.</Text>}
    />
  );
}

const styles = StyleSheet.create({
  list: { padding: 12, gap: 8 },
  item: {
    flexDirection: 'row',
    gap: 10,
    backgroundColor: colors.card,
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  dot: { width: 10, height: 10, borderRadius: 5, marginTop: 5 },
  body: { flex: 1, gap: 2 },
  message: { color: colors.text, fontSize: 15 },
  meta: { color: colors.muted, fontSize: 12 },
  photo: { width: '100%', aspectRatio: 4 / 3, marginTop: 8, borderRadius: 8, backgroundColor: '#000' },
  empty: { color: colors.muted, padding: 24, textAlign: 'center' },
});
