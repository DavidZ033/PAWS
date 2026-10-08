import React, { useCallback, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../api/client';
import { CameraView } from '../components/CameraView';
import { Joystick } from '../components/Joystick';
import { Button } from '../components/ui';
import { useRobot } from '../state/RobotContext';
import { colors, timeAgo } from '../theme';

const SPEEDS = [0.3, 0.6, 1.0];

export function ControlScreen() {
  const { client, socket, status, connection } = useRobot();
  const [speed, setSpeed] = useState(0.6);
  const [note, setNote] = useState('');

  const online = connection === 'connected';

  // Left stick slides the robot. Stick up is forward; stick right is the
  // robot's right, which is negative vy in the robot's convention.
  const onMoveStick = useCallback(
    (x: number, y: number) => socket?.setDrive({ vx: y * speed, vy: -x * speed }),
    [socket, speed],
  );
  // Right stick turns. Stick right is clockwise, which is negative omega.
  const onTurnStick = useCallback((x: number) => socket?.setDrive({ omega: -x * speed * 0.7 }), [socket, speed]);

  const run = async (label: string, action: () => Promise<unknown>) => {
    try {
      await action();
      setNote(label);
    } catch (error) {
      setNote(error instanceof ApiError ? error.message : 'Something went wrong');
    }
  };

  const detection = status?.detection;
  let dogLine = 'Dog detection off';
  if (detection?.available && detection.enabled) {
    dogLine = detection.dog_present ? 'Dog in view' : `No dog in view (last seen ${timeAgo(detection.last_seen)})`;
  } else if (detection && !detection.available) {
    dogLine = 'Dog detection unavailable';
  }

  return (
    <View style={styles.screen}>
      <CameraView
        streamUrl={online && client ? client.streamUrl() : null}
        message={online && status && !status.camera.available ? 'Camera unavailable' : null}
      />

      <View style={styles.statusBar}>
        <Text style={[styles.statusText, detection?.dog_present && { color: colors.good }]}>{dogLine}</Text>
        {status ? (
          <Text style={styles.statusText}>
            x {status.pose.x.toFixed(2)} m, y {status.pose.y.toFixed(2)} m, {status.pose.theta_deg.toFixed(0)} deg
            {status.mode === 'auto' ? '  (auto)' : ''}
            {status.simulated ? '  (simulation)' : ''}
          </Text>
        ) : (
          <Text style={styles.statusText}>{connection === 'connecting' ? 'Connecting...' : 'Not connected'}</Text>
        )}
        {note ? <Text style={styles.note}>{note}</Text> : null}
      </View>

      <View style={styles.actions}>
        <Button
          title={status?.feeder.busy ? 'Feeding...' : 'Feed'}
          color={colors.good}
          disabled={!online || status?.feeder.busy}
          onPress={() => run('Dispensed 1 portion', () => client!.feed(1))}
          style={styles.action}
        />
        <Button
          title={status?.launcher.running ? 'Launching...' : 'Launch ball'}
          color={colors.warn}
          disabled={!online}
          onPress={() => run('Launcher fired', () => client!.launch())}
          style={styles.action}
        />
        <Button
          title="Go home"
          disabled={!online}
          onPress={() => run('Driving back to start', () => client!.goto({ x: 0, y: 0, theta: 0 }))}
          style={styles.action}
        />
      </View>

      <View style={styles.speedRow}>
        <Text style={styles.statusText}>Speed</Text>
        {SPEEDS.map((value) => (
          <Button
            key={value}
            title={`${Math.round(value * 100)}%`}
            color={value === speed ? colors.primary : colors.card}
            onPress={() => setSpeed(value)}
            style={styles.speed}
          />
        ))}
      </View>

      <View style={styles.sticks}>
        <Joystick label="Move" onMove={onMoveStick} />
        <Joystick label="Turn" horizontalOnly onMove={onTurnStick} />
      </View>

      <Button
        title="STOP"
        color={colors.danger}
        disabled={!online}
        onPress={() => {
          socket?.stop();
          setNote('Stopped');
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: 12, gap: 10 },
  statusBar: { gap: 2 },
  statusText: { color: colors.muted, fontSize: 13 },
  note: { color: colors.text, fontSize: 13 },
  actions: { flexDirection: 'row', gap: 8 },
  action: { flex: 1 },
  speedRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  speed: { paddingVertical: 6, paddingHorizontal: 14, borderWidth: 1, borderColor: colors.border },
  sticks: { flex: 1, flexDirection: 'row', justifyContent: 'space-around', alignItems: 'center', minHeight: 160 },
});
