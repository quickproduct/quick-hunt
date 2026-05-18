import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../context/ThemeContext';

function getStrength(password: string): { score: number; label: string } {
  if (!password) return { score: 0, label: '' };
  let score = 0;
  if (password.length >= 8) score++;
  if (/[A-Z]/.test(password)) score++;
  if (/[0-9]/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;
  const labels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
  return { score, label: labels[score] ?? 'Strong' };
}

export default function PasswordStrengthBar({ password }: { password: string }) {
  const { colors } = useTheme();
  const { score, label } = getStrength(password);

  const segmentColors = [
    score >= 1 ? (score === 1 ? colors.error : score === 2 ? colors.warning : colors.success) : colors.border,
    score >= 2 ? (score === 2 ? colors.warning : colors.success) : colors.border,
    score >= 3 ? colors.success : colors.border,
    score >= 4 ? colors.success : colors.border,
  ];

  const labelColor =
    score <= 1 ? colors.error : score === 2 ? colors.warning : colors.success;

  if (!password) return null;

  return (
    <View style={styles.container}>
      <View style={styles.bars}>
        {segmentColors.map((color, i) => (
          <View key={i} style={[styles.bar, { backgroundColor: color }]} />
        ))}
      </View>
      <Text style={[styles.label, { color: labelColor }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    marginTop: 6,
  },
  bars: {
    flex: 1,
    flexDirection: 'row',
    gap: 4,
  },
  bar: {
    borderRadius: 4,
    flex: 1,
    height: 4,
  },
  label: {
    fontSize: 11,
    fontWeight: '700',
    width: 44,
  },
});
