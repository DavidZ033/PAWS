// Live video from the robot.
//
// The robot serves MJPEG, which is just a never-ending series of JPEGs.
// React Native's <Image> cannot play that, but a browser <img> tag can, so
// on phones the stream is shown inside a tiny web view. When the app runs
// in a browser, CameraView.web.tsx is used instead.

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { WebView } from 'react-native-webview';

import { colors } from '../theme';

interface Props {
  streamUrl: string | null;
  /** Shown instead of video, for example "Camera unavailable". */
  message?: string | null;
}

export function CameraView({ streamUrl, message }: Props) {
  let content: React.ReactNode;
  if (!streamUrl || message) {
    content = <Text style={styles.message}>{message ?? 'Not connected'}</Text>;
  } else {
    const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
      <body style="margin:0;background:#000;height:100vh;display:flex;align-items:center;justify-content:center">
      <img src="${streamUrl}" style="width:100%;height:100%;object-fit:contain" />
      </body></html>`;
    content = (
      <WebView
        key={streamUrl}
        source={{ html }}
        originWhitelist={['*']}
        style={styles.web}
        scrollEnabled={false}
        mixedContentMode="always"
        allowsInlineMediaPlayback
      />
    );
  }
  return <View style={styles.frame}>{content}</View>;
}

const styles = StyleSheet.create({
  frame: {
    width: '100%',
    aspectRatio: 4 / 3,
    backgroundColor: '#000',
    borderRadius: 10,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  web: { flex: 1, alignSelf: 'stretch', backgroundColor: '#000' },
  message: { color: colors.muted, padding: 16, textAlign: 'center' },
});
