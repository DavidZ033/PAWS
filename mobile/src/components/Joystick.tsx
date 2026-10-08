// A simple on-screen joystick. Reports x and y from -1 to 1 while held and
// (0, 0) on release. x is right-positive, y is up-positive.

import React, { useMemo, useRef, useState } from 'react';
import { PanResponder, StyleSheet, Text, View } from 'react-native';

import { colors } from '../theme';

interface Props {
  size?: number;
  /** Lock movement to the horizontal axis (used for the turn stick). */
  horizontalOnly?: boolean;
  label?: string;
  onMove: (x: number, y: number) => void;
}

export function Joystick({ size = 150, horizontalOnly = false, label, onMove }: Props) {
  const [knob, setKnob] = useState({ x: 0, y: 0 });
  const callback = useRef(onMove);
  callback.current = onMove;
  const radius = size / 2;
  const knobSize = size * 0.42;

  const responder = useMemo(() => {
    const update = (dx: number, dy: number) => {
      let x = dx / radius;
      let y = horizontalOnly ? 0 : -dy / radius;
      const length = Math.hypot(x, y);
      if (length > 1) {
        x /= length;
        y /= length;
      }
      setKnob({ x, y });
      // Small dead zone so a resting thumb does not creep the robot.
      const dead = (v: number) => (Math.abs(v) < 0.08 ? 0 : Math.round(v * 100) / 100);
      callback.current(dead(x), dead(y));
    };
    const release = () => {
      setKnob({ x: 0, y: 0 });
      callback.current(0, 0);
    };
    return PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderTerminationRequest: () => false,
      onPanResponderMove: (_, gesture) => update(gesture.dx, gesture.dy),
      onPanResponderRelease: release,
      onPanResponderTerminate: release,
    });
  }, [radius, horizontalOnly]);

  return (
    <View style={styles.wrap}>
      <View
        {...responder.panHandlers}
        style={[styles.base, { width: size, height: horizontalOnly ? knobSize + 16 : size, borderRadius: radius }]}
      >
        <View
          pointerEvents="none"
          style={[
            styles.knob,
            {
              width: knobSize,
              height: knobSize,
              borderRadius: knobSize / 2,
              transform: [{ translateX: knob.x * (radius - knobSize / 2) }, { translateY: -knob.y * (radius - knobSize / 2) }],
            },
          ]}
        />
      </View>
      {label ? <Text style={styles.label}>{label}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center' },
  base: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  knob: { backgroundColor: colors.primary },
  label: { color: colors.muted, marginTop: 6, fontSize: 12 },
});
