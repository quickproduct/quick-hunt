import React from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  StyleProp,
  StyleSheet,
  Text,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { Button as PaperButton, Chip as PaperChip, Surface, TouchableRipple } from 'react-native-paper';
import { useTheme } from '../context/ThemeContext';

type IconName = keyof typeof Ionicons.glyphMap;

function animateIn(delay: number) {
  const opacity = React.useRef(new Animated.Value(delay > 0 ? 0 : 1)).current;
  const translateY = React.useRef(new Animated.Value(delay > 0 ? 10 : 0)).current;

  React.useEffect(() => {
    if (delay <= 0) return;
    const animation = Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 260, delay, useNativeDriver: true }),
      Animated.timing(translateY, { toValue: 0, duration: 260, delay, useNativeDriver: true }),
    ]);
    animation.start();
    return () => animation.stop();
  }, [delay, opacity, translateY]);

  return { opacity, translateY };
}

export const GlassCard = React.memo(function GlassCard({
  children,
  style,
  delay = 0,
  padded = true,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  delay?: number;
  padded?: boolean;
}) {
  const { colors, isDark } = useTheme();
  const { opacity, translateY } = animateIn(delay);

  return (
    <Animated.View style={{ opacity, transform: [{ translateY }] }}>
      <Surface
        elevation={2}
        style={[
          styles.cardShadow,
          {
            backgroundColor: isDark ? colors.glass : colors.surface,
            borderColor: colors.border,
            shadowColor: colors.shadow,
          },
          style,
        ]}
      >
        <BlurView intensity={isDark ? 48 : 42} tint={isDark ? 'dark' : 'light'} style={StyleSheet.absoluteFill} />
        <LinearGradient
          colors={isDark ? ['rgba(255,255,255,0.08)', 'rgba(255,255,255,0.02)'] : ['rgba(255,255,255,0.68)', 'rgba(255,255,255,0.18)']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={StyleSheet.absoluteFill}
        />
        <View style={[styles.cardContent, padded && styles.cardPadding]}>{children}</View>
      </Surface>
    </Animated.View>
  );
});

export const SectionCard = React.memo(function SectionCard({
  children,
  style,
  padded = true,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  padded?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <Surface style={[styles.sectionCard, { backgroundColor: colors.surfaceStrong, borderColor: colors.border }, style]} elevation={1}>
      <View style={[padded && styles.cardPadding]}>{children}</View>
    </Surface>
  );
});

export const PageHeader = React.memo(function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.pageHeader}>
      <View style={styles.pageHeaderText}>
        <Text style={[styles.pageHeaderTitle, { color: colors.text }]}>{title}</Text>
        {subtitle ? <Text style={[styles.pageHeaderSubtitle, { color: colors.textMuted }]}>{subtitle}</Text> : null}
      </View>
      {action}
    </View>
  );
});

export const SectionHeader = React.memo(function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  const { colors } = useTheme();

  return (
    <View style={styles.sectionHeader}>
      <View style={styles.sectionTitleWrap}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>{title}</Text>
        {subtitle ? <Text style={[styles.sectionSubtitle, { color: colors.textMuted }]}>{subtitle}</Text> : null}
      </View>
      {action}
    </View>
  );
});

export const StatTile = React.memo(function StatTile({
  label,
  value,
  icon,
  accent = 'primary',
  style,
  onPress,
}: {
  label: string;
  value: string | number;
  icon: IconName;
  accent?: 'primary' | 'mint' | 'amber' | 'coral';
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
}) {
  const { colors } = useTheme();
  const accentColor =
    accent === 'mint'
      ? colors.accentMint
      : accent === 'amber'
        ? colors.accentAmber
        : accent === 'coral'
          ? colors.accentCoral
          : colors.primary;

  const content = (
    <View style={[styles.statTile, style]}>
      <View style={[styles.iconBox, { backgroundColor: accentColor }]}>
        <Ionicons name={icon} size={16} color={colors.primaryText} />
      </View>
      <Text style={[styles.statValue, { color: colors.text }]} numberOfLines={1}>
        {value}
      </Text>
      <Text style={[styles.statLabel, { color: colors.textMuted }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );

  if (onPress) {
    return (
      <TouchableRipple onPress={onPress} borderless={false} style={styles.rippleRadius}>
        <GlassCard>{content}</GlassCard>
      </TouchableRipple>
    );
  }

  return <GlassCard>{content}</GlassCard>;
});

export const StatusPill = React.memo(function StatusPill({
  label,
  tone = 'neutral',
  compact = false,
}: {
  label: string;
  tone?: 'mint' | 'cyan' | 'amber' | 'coral' | 'neutral';
  compact?: boolean;
}) {
  const { colors, isDark } = useTheme();
  const palette = {
    mint: [isDark ? 'rgba(95, 240, 178, 0.17)' : '#DBFBEF', colors.success],
    cyan: [isDark ? 'rgba(103, 232, 249, 0.17)' : '#DDFBFF', colors.primary],
    amber: [isDark ? 'rgba(250, 211, 107, 0.17)' : '#FFF2C6', colors.warning],
    coral: [isDark ? 'rgba(255, 122, 112, 0.17)' : '#FFE0DA', colors.error],
    neutral: [isDark ? 'rgba(255, 255, 255, 0.08)' : '#E9EEF5', colors.textMuted],
  } as const;
  const [bg, fg] = palette[tone];

  return (
    <View style={[styles.pill, compact && styles.pillCompact, { backgroundColor: bg, borderColor: colors.border }]}>
      <Text style={[styles.pillText, compact && styles.pillTextCompact, { color: fg }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
});

export const FilterChip = React.memo(function FilterChip({
  label,
  active,
  onPress,
  icon,
  count,
}: {
  label: string;
  active?: boolean;
  onPress?: () => void;
  icon?: IconName;
  count?: number;
}) {
  const { colors } = useTheme();
  const chipLabel = count !== undefined ? `${label} (${count})` : label;

  return (
    <PaperChip
      selected={!!active}
      compact={false}
      mode="flat"
      icon={icon ? ({ size, color }) => <Ionicons name={icon} size={size} color={color} /> : undefined}
      onPress={onPress}
      textStyle={[
        styles.chipText,
        { color: active ? colors.primaryText : colors.textSecondary },
      ]}
      style={[
        styles.chip,
        {
          backgroundColor: active ? colors.primary : colors.input,
          borderColor: active ? colors.primary : colors.border,
        },
      ]}
      rippleColor={colors.primarySoft}
      showSelectedCheck={false}
    >
      {chipLabel}
    </PaperChip>
  );
});

export const AppButton = React.memo(function AppButton({
  label,
  onPress,
  icon,
  variant = 'primary',
  disabled,
  loading,
  style,
  badge,
}: {
  label: string;
  onPress?: () => void;
  icon?: IconName;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
  badge?: number;
}) {
  const { colors } = useTheme();
  const buttonMode = variant === 'primary' ? 'contained' : 'contained-tonal';
  const backgroundColor =
    variant === 'primary'
      ? colors.primary
      : variant === 'danger'
        ? 'rgba(255,122,112,0.14)'
        : colors.input;
  const color = variant === 'primary' ? colors.primaryText : variant === 'danger' ? colors.error : colors.textSecondary;

  return (
    <View style={[styles.buttonWrap, style]}>
      <PaperButton
        mode={buttonMode}
        onPress={onPress}
        disabled={disabled || loading}
        loading={loading}
        icon={icon ? ({ size, color: iconColor }) => <Ionicons name={icon} size={size} color={iconColor} /> : undefined}
        buttonColor={backgroundColor}
        textColor={color}
        contentStyle={styles.buttonContent}
        labelStyle={styles.buttonText}
        style={[
          styles.button,
          {
            borderColor: variant === 'primary' ? 'rgba(255,255,255,0.18)' : colors.border,
            shadowColor: variant === 'primary' ? colors.primary : colors.shadow,
          },
        ]}
      >
        {label}
      </PaperButton>
      {badge !== undefined && badge > 0 ? (
        <View style={[styles.badge, { backgroundColor: colors.error }]}>
          <Text style={styles.badgeText}>{badge > 99 ? '99+' : badge}</Text>
        </View>
      ) : null}
    </View>
  );
});

export const EmptyState = React.memo(function EmptyState({
  title,
  message,
  icon = 'sparkles-outline',
  action,
}: {
  title: string;
  message: string;
  icon?: IconName;
  action?: React.ReactNode;
}) {
  const { colors } = useTheme();

  return (
    <SectionCard style={styles.emptyState}>
      <View style={[styles.emptyIcon, { backgroundColor: colors.primarySoft }]}>
        <Ionicons name={icon} size={24} color={colors.primary} />
      </View>
      <Text style={[styles.emptyTitle, { color: colors.text }]}>{title}</Text>
      <Text style={[styles.emptyMessage, { color: colors.textMuted }]}>{message}</Text>
      {action}
    </SectionCard>
  );
});

export const ScreenError = React.memo(function ScreenError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <EmptyState
      icon="alert-circle-outline"
      title="Could not load data"
      message={message}
      action={<AppButton label="Retry" icon="refresh-outline" onPress={onRetry} style={styles.emptyAction} />}
    />
  );
});

export const KeyValueRow = React.memo(function KeyValueRow({
  label,
  value,
  valueStyle,
}: {
  label: string;
  value?: string | number | null;
  valueStyle?: StyleProp<TextStyle>;
}) {
  const { colors } = useTheme();
  return (
    <View style={[styles.keyValueRow, { borderBottomColor: colors.border }]}>
      <Text style={[styles.keyLabel, { color: colors.textMuted }]}>{label}</Text>
      <Text style={[styles.keyValue, { color: colors.text }, valueStyle]} numberOfLines={2}>
        {value || '-'}
      </Text>
    </View>
  );
});

export const FormField = React.memo(function FormField({
  label,
  children,
  helper,
}: {
  label: string;
  children: React.ReactNode;
  helper?: string;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.formField}>
      <Text style={[styles.formLabel, { color: colors.textMuted }]}>{label}</Text>
      {children}
      {helper ? <Text style={[styles.formHelper, { color: colors.textMuted }]}>{helper}</Text> : null}
    </View>
  );
});

export const Divider = React.memo(function Divider({ style }: { style?: StyleProp<ViewStyle> }) {
  const { colors } = useTheme();
  return <View style={[{ height: StyleSheet.hairlineWidth, backgroundColor: colors.border }, style]} />;
});

export const SkeletonBlock = React.memo(function SkeletonBlock({
  width = '100%',
  height = 16,
  radius = 12,
  style,
}: {
  width?: number | `${number}%`;
  height?: number;
  radius?: number;
  style?: StyleProp<ViewStyle>;
}) {
  const { colors, isDark } = useTheme();
  const opacity = React.useRef(new Animated.Value(0.42)).current;

  React.useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.86, duration: 820, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.42, duration: 820, useNativeDriver: true }),
      ])
    );
    animation.start();
    return () => animation.stop();
  }, [opacity]);

  return (
    <Animated.View
      style={[
        {
          width,
          height,
          borderRadius: radius,
          backgroundColor: isDark ? 'rgba(255,255,255,0.12)' : colors.input,
          opacity,
        },
        style,
      ]}
    />
  );
});

const styles = StyleSheet.create({
  cardShadow: {
    borderRadius: 24,
    borderWidth: 1,
    overflow: 'hidden',
    shadowOffset: { width: 0, height: 16 },
    shadowOpacity: 0.28,
    shadowRadius: 24,
  },
  sectionCard: {
    borderRadius: 24,
    borderWidth: 1,
    overflow: 'hidden',
  },
  cardContent: {
    position: 'relative',
  },
  cardPadding: {
    padding: 18,
  },
  pageHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 18,
    paddingTop: 8,
  },
  pageHeaderText: {
    flex: 1,
  },
  pageHeaderTitle: {
    fontSize: 31,
    fontWeight: '900',
    letterSpacing: 0,
  },
  pageHeaderSubtitle: {
    fontSize: 13,
    fontWeight: '700',
    marginTop: 4,
  },
  sectionHeader: {
    alignItems: 'flex-end',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 14,
    marginTop: 2,
  },
  sectionTitleWrap: {
    flex: 1,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '900',
  },
  sectionSubtitle: {
    fontSize: 12,
    fontWeight: '700',
    marginTop: 3,
  },
  statTile: {
    minHeight: 116,
    width: '100%',
  },
  iconBox: {
    alignItems: 'center',
    borderRadius: 16,
    height: 42,
    justifyContent: 'center',
    marginBottom: 14,
    width: 42,
  },
  statValue: {
    fontSize: 24,
    fontWeight: '900',
  },
  statLabel: {
    fontSize: 12,
    fontWeight: '700',
    marginTop: 4,
  },
  pill: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 11,
    paddingVertical: 6,
  },
  pillCompact: {
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  pillText: {
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'capitalize',
  },
  pillTextCompact: {
    fontSize: 10,
  },
  chip: {
    borderWidth: 1,
    minHeight: 42,
  },
  chipText: {
    fontSize: 12,
    fontWeight: '800',
  },
  buttonWrap: {
    position: 'relative',
  },
  button: {
    borderRadius: 18,
    borderWidth: 1,
  },
  buttonContent: {
    minHeight: 52,
    paddingHorizontal: 8,
  },
  buttonText: {
    fontSize: 14,
    fontWeight: '900',
  },
  badge: {
    alignItems: 'center',
    borderRadius: 10,
    height: 20,
    justifyContent: 'center',
    minWidth: 20,
    paddingHorizontal: 4,
    position: 'absolute',
    right: -4,
    top: -4,
  },
  badgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '900',
  },
  emptyState: {
    alignItems: 'center',
    marginTop: 16,
    padding: 28,
  },
  emptyIcon: {
    alignItems: 'center',
    borderRadius: 18,
    height: 54,
    justifyContent: 'center',
    marginBottom: 14,
    width: 54,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '800',
    marginBottom: 6,
    textAlign: 'center',
  },
  emptyMessage: {
    fontSize: 13,
    fontWeight: '500',
    lineHeight: 19,
    marginBottom: 16,
    textAlign: 'center',
  },
  emptyAction: {
    minWidth: 128,
  },
  keyValueRow: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    paddingVertical: 12,
  },
  keyLabel: {
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  keyValue: {
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
  },
  formField: {
    marginBottom: 14,
  },
  formLabel: {
    fontSize: 12,
    fontWeight: '900',
    marginBottom: 8,
    textTransform: 'uppercase',
  },
  formHelper: {
    fontSize: 12,
    fontWeight: '600',
    marginTop: 6,
  },
  rippleRadius: {
    borderRadius: 24,
  },
});
