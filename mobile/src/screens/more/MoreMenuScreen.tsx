import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import SVGBackground from '../../components/SVGBackground';
import { GlassCard } from '../../components/GlassKit';
import { useTheme } from '../../context/ThemeContext';
import { useAuthStore } from '../../store/authStore';
import { MoreStackParamList } from '../../navigation/AppNavigator';

type Nav = NativeStackNavigationProp<MoreStackParamList, 'MoreMenu'>;

type MenuItem = {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  screen: keyof MoreStackParamList;
  adminOnly?: boolean;
  ownerOnly?: boolean;
  accent?: string;
};

const MENU_ITEMS: MenuItem[] = [
  { label: 'Send Logs', icon: 'mail-outline', screen: 'Logs' },
  { label: 'Direct HR Send', icon: 'paper-plane-outline', screen: 'DirectSend' },
  { label: 'Company Blacklist', icon: 'ban-outline', screen: 'Blacklist' },
  { label: 'Profile', icon: 'person-circle-outline', screen: 'Profile' },
  { label: 'Settings', icon: 'settings-outline', screen: 'Settings' },
  { label: 'Billing', icon: 'card-outline', screen: 'Billing', ownerOnly: true },
  { label: 'API Quotas', icon: 'speedometer-outline', screen: 'AdminQuota', adminOnly: true },
  { label: 'Admin Panel', icon: 'shield-checkmark-outline', screen: 'Admin', adminOnly: true, accent: '#FF6B5F' },
];

export default function MoreMenuScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<Nav>();
  const { user } = useAuthStore();

  const isAdmin = user?.role === 'admin' || user?.role === 'owner';
  const isOwner = user?.role === 'owner';

  const visible = MENU_ITEMS.filter((item) => {
    if (item.adminOnly && !isAdmin) return false;
    if (item.ownerOnly && !isOwner) return false;
    return true;
  });

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          <Text style={[styles.title, { color: colors.text }]}>More</Text>
          <Text style={[styles.subtitle, { color: colors.textMuted }]}>Tools & settings</Text>

          <GlassCard style={styles.menu} padded={false}>
            {visible.map((item, i) => (
              <Pressable
                key={item.screen}
                onPress={() => navigation.navigate(item.screen as any)}
                style={({ pressed }) => [
                  styles.row,
                  {
                    borderBottomColor: colors.border,
                    borderBottomWidth: i < visible.length - 1 ? StyleSheet.hairlineWidth : 0,
                    opacity: pressed ? 0.78 : 1,
                    transform: [{ scale: pressed ? 0.99 : 1 }],
                  },
                ]}
              >
                <View style={[styles.iconWrap, { backgroundColor: item.accent ? `${item.accent}22` : colors.primarySoft }]}>
                  <Ionicons name={item.icon} size={20} color={item.accent ?? colors.primary} />
                </View>
                <Text style={[styles.label, { color: item.accent ?? colors.text }]}>{item.label}</Text>
                <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
              </Pressable>
            ))}
          </GlassCard>
        </ScrollView>
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  content: { padding: 20, paddingBottom: 118 },
  title: { fontSize: 30, fontWeight: '900', marginTop: 10 },
  subtitle: { fontSize: 12, fontWeight: '700', marginBottom: 24, marginTop: 4 },
  menu: { overflow: 'hidden' },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 14,
    paddingHorizontal: 16,
    paddingVertical: 17,
  },
  iconWrap: { alignItems: 'center', borderRadius: 14, height: 40, justifyContent: 'center', width: 40 },
  label: { flex: 1, fontSize: 15, fontWeight: '800' },
});
