import React from 'react';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuthStore } from '../../store/authStore';
import { useTheme } from '../../context/ThemeContext';
import SVGBackground from '../../components/SVGBackground';

export default function LoadingScreen() {
  const { isLoading } = useAuthStore();
  const { colors } = useTheme();

  return (
    <SVGBackground>
      <View style={styles.container}>
        <View style={[styles.content, { backgroundColor: colors.glass, borderColor: colors.border }]}>
          <View style={[styles.logo, { backgroundColor: colors.primarySoft }]}>
            <Ionicons name="sparkles" size={26} color={colors.primary} />
          </View>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[styles.text, { color: colors.textMuted }]}>
            {isLoading ? 'Loading...' : 'QuickHunt'}
          </Text>
        </View>
      </View>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  content: {
    alignItems: 'center',
    borderRadius: 28,
    borderWidth: 1,
    minWidth: 180,
    padding: 28,
  },
  logo: {
    alignItems: 'center',
    borderRadius: 20,
    height: 56,
    justifyContent: 'center',
    marginBottom: 18,
    width: 56,
  },
  text: {
    marginTop: 16,
    fontSize: 15,
    fontWeight: '800',
  },
});
