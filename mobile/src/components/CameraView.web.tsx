// Browser version of CameraView. A plain <img> tag plays MJPEG directly.

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors } from '../theme';

interface Props {
  streamUrl: string | null;
  message?: string | null;
}

export function CameraView({ streamUrl, message }: Props) {
  return (
    <View style={styles.frame}>
      {!streamUrl || message ? (
        <Text style={styles.message}>{message ?? 'Not connected'}</Text>
      ) : (
        React.createElement('img', {
          src: streamUrl,
          alt: 'Live camera',
          style: { width: '100%', height: '100%', objectFit: 'contain' },
        })
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    width: '100%',
    aspectRatio: 4 / 3,
    maxHeight: 300,
    backgroundColor: '#000',
    borderRadius: 10,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  message: { color: colors.muted, padding: 16, textAlign: 'center' },
});
