import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { ApiError, PawsClient } from '../api/client';
import { Button, Card, Row } from '../components/ui';
import { useRobot } from '../state/RobotContext';
import { colors, timeAgo } from '../theme';

export function SettingsScreen() {
  const { settings, saveSettings, client, status, connection } = useRobot();
  const [host, setHost] = useState(settings.host);
  const [port, setPort] = useState(String(settings.port));
  const [token, setToken] = useState(settings.token);
  const [message, setMessage] = useState('');

  // Show saved values once they have been loaded from the phone.
  useEffect(() => {
    setHost(settings.host);
    setPort(String(settings.port));
    setToken(settings.token);
  }, [settings]);

  const connect = async () => {
    const next = { host: host.trim(), port: Number(port) || 8000, token: token.trim() };
    if (!next.host) {
      setMessage("Enter the robot's IP address, for example 192.168.1.50");
      return;
    }
    setMessage('Checking...');
    try {
      const reply = await new PawsClient(next).status();
      setMessage(`Found ${reply.name} v${reply.version}${reply.simulated ? ' (simulation)' : ''}`);
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : 'Could not connect');
    }
    // Save even if the check failed, so the app keeps retrying that address.
    await saveSettings(next);
  };

  const act = async (action: () => Promise<unknown>, done: string) => {
    try {
      await action();
      setMessage(done);
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : 'Request failed');
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.screen} keyboardShouldPersistTaps="handled">
      <Text style={styles.heading}>Robot connection</Text>
      <Card style={styles.form}>
        <Text style={styles.muted}>Robot IP address or hostname</Text>
        <TextInput
          value={host}
          onChangeText={setHost}
          placeholder="192.168.1.50 or raspberrypi.local"
          placeholderTextColor={colors.muted}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          style={styles.input}
        />
        <Text style={styles.muted}>Port</Text>
        <TextInput value={port} onChangeText={setPort} keyboardType="number-pad" style={styles.input} />
        <Text style={styles.muted}>Token (only if one is set in config.yaml)</Text>
        <TextInput
          value={token}
          onChangeText={setToken}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          style={styles.input}
        />
        <Button title="Save and connect" onPress={connect} />
        {message ? <Text style={styles.message}>{message}</Text> : null}
      </Card>
      <Text style={styles.muted}>
        Your phone and the robot must be on the same WiFi network. Find the robot's address by running "hostname -I"
        on the Pi.
      </Text>

      <Text style={styles.heading}>Robot</Text>
      <Card>
        <Row label="Connection" value={connection} />
        {status ? (
          <>
            <Row label="Name" value={`${status.name} v${status.version}${status.simulated ? ' (simulation)' : ''}`} />
            <Row label="Camera" value={status.camera.available ? status.camera.backend : status.camera.error ?? 'unavailable'} />
            <Row label="Last fed" value={timeAgo(status.feeder.last_fed)} />
            <Row label="Portions dispensed" value={String(status.feeder.total_portions)} />
            <Row
              label="Dog detection"
              value={status.detection.available ? (status.detection.enabled ? 'on' : 'off') : status.detection.reason ?? 'unavailable'}
            />
          </>
        ) : null}
      </Card>

      {status && client ? (
        <Card style={styles.form}>
          <View style={styles.switchRow}>
            <Text style={styles.label}>Dog detection</Text>
            <Switch
              value={status.detection.enabled}
              disabled={!status.detection.available}
              onValueChange={(enabled) => act(() => client.setDetection(enabled), `Detection ${enabled ? 'on' : 'off'}`)}
            />
          </View>
          <Button
            title="Set current spot as home"
            color={colors.border}
            onPress={() => act(() => client.resetPose(), 'Home position reset')}
          />
          <Button
            title="Cancel navigation"
            color={colors.border}
            onPress={() => act(() => client.cancelNavigation(), 'Navigation cancelled')}
          />
        </Card>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { padding: 12, gap: 10 },
  heading: { color: colors.text, fontSize: 18, fontWeight: '700', marginTop: 6 },
  muted: { color: colors.muted, fontSize: 13 },
  label: { color: colors.text, fontSize: 15 },
  message: { color: colors.text },
  form: { gap: 10 },
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  input: {
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
  },
});
