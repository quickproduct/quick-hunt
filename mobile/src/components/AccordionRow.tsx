import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';

interface AccordionRowProps {
  title: string;
  /** Smaller muted line displayed below the title */
  subtitle?: string;
  /** Pill label displayed on the right side of the header (e.g. "3 failed") */
  badge?: string;
  /** Background color for the badge pill (defaults to colors.warning) */
  badgeColor?: string;
  children: React.ReactNode;
  initialOpen?: boolean;
}

export default function AccordionRow({
  title,
  subtitle,
  badge,
  badgeColor,
  children,
  initialOpen = false,
}: AccordionRowProps) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(initialOpen);
  const pillBg = badgeColor ?? colors.warning;

  return (
    <View style={[styles.container, { borderBottomColor: colors.border }]}>
      <Pressable
        onPress={() => setOpen((v) => !v)}
        style={({ pressed }) => [styles.header, { opacity: pressed ? 0.78 : 1, transform: [{ scale: pressed ? 0.99 : 1 }] }]}
      >
        {/* Left: title + optional subtitle */}
        <View style={styles.titleBlock}>
          <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
          {subtitle ? (
            <Text style={[styles.subtitle, { color: colors.textMuted }]}>{subtitle}</Text>
          ) : null}
        </View>

        {/* Right: optional badge pill + chevron */}
        <View style={styles.rightRow}>
          {badge ? (
            <View style={[styles.badgePill, { backgroundColor: pillBg }]}>
              <Text style={styles.badgeText}>{badge}</Text>
            </View>
          ) : null}
          <Ionicons
            name={open ? 'chevron-up' : 'chevron-down'}
            size={16}
            color={colors.textMuted}
          />
        </View>
      </Pressable>

      {open && <View style={styles.body}>{children}</View>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 14,
    gap: 8,
  },
  titleBlock: {
    flex: 1,
    gap: 2,
  },
  title: {
    fontSize: 14,
    fontWeight: '900',
  },
  subtitle: {
    fontSize: 11,
    fontWeight: '600',
  },
  rightRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  badgePill: {
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  badgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '800',
  },
  body: {
    paddingBottom: 14,
  },
});
