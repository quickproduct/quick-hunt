import React from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Defs, Line, LinearGradient, Path, Rect, Stop } from 'react-native-svg';
import { useTheme } from '../context/ThemeContext';

export default React.memo(function SVGBackground({ children }: { children: React.ReactNode }) {
  const { colors, isDark } = useTheme();

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <Svg style={StyleSheet.absoluteFill} height="100%" width="100%" viewBox="0 0 360 800" preserveAspectRatio="xMidYMid slice">
        <Defs>
          <LinearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
            <Stop offset="0" stopColor={colors.backgroundTop} />
            <Stop offset="0.48" stopColor={colors.background} />
            <Stop offset="1" stopColor={colors.backgroundBottom} />
          </LinearGradient>
          <LinearGradient id="cinema" x1="0" x2="1" y1="0" y2="0">
            <Stop offset="0" stopColor={colors.primary} stopOpacity={isDark ? 0.2 : 0.16} />
            <Stop offset="0.5" stopColor={colors.accentMint} stopOpacity={isDark ? 0.08 : 0.1} />
            <Stop offset="1" stopColor={colors.accentCoral} stopOpacity={isDark ? 0.13 : 0.1} />
          </LinearGradient>
          <LinearGradient id="stage" x1="0" x2="0" y1="0" y2="1">
            <Stop offset="0" stopColor="#FFFFFF" stopOpacity={isDark ? 0.08 : 0.35} />
            <Stop offset="0.42" stopColor="#FFFFFF" stopOpacity={isDark ? 0.02 : 0.12} />
            <Stop offset="1" stopColor="#000000" stopOpacity={isDark ? 0.32 : 0.04} />
          </LinearGradient>
        </Defs>
        <Rect width="360" height="800" fill="url(#bg)" />
        <Rect width="360" height="800" fill="url(#cinema)" />
        <Rect width="360" height="800" fill="url(#stage)" />
        <Rect x="12" y="22" width="336" height="728" rx="38" fill="#FFFFFF" opacity={isDark ? 0.025 : 0.12} />
        <Rect x="28" y="44" width="304" height="680" rx="32" fill="#FFFFFF" opacity={isDark ? 0.018 : 0.08} />
        <Path
          d="M-20 118 C64 80 118 94 184 122 C250 150 298 146 384 96 M-18 306 C78 270 128 284 198 318 C260 348 306 346 382 316 M-28 596 C64 554 128 564 196 602 C256 636 306 638 388 598"
          stroke="url(#cinema)"
          strokeWidth="1.2"
          fill="none"
          opacity={isDark ? 0.42 : 0.36}
        />
        {Array.from({ length: 9 }).map((_, index) => (
          <Line
            key={index}
            x1={-24}
            y1={130 + index * 58}
            x2={384}
            y2={82 + index * 58}
            stroke="#FFFFFF"
            strokeWidth="0.8"
            opacity={isDark ? 0.035 : 0.12}
          />
        ))}
        {Array.from({ length: 6 }).map((_, index) => (
          <Line
            key={`rail-${index}`}
            x1={36 + index * 56}
            y1={0}
            x2={-18 + index * 56}
            y2={800}
            stroke={colors.primary}
            strokeWidth="0.6"
            opacity={isDark ? 0.04 : 0.09}
          />
        ))}
      </Svg>
      <View style={styles.content}>{children}</View>
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    flex: 1,
    overflow: 'hidden',
  },
  content: {
    flex: 1,
  },
});
