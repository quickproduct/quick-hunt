import React from 'react';
import { ScrollView, StyleSheet, Text } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import SVGBackground from '../../components/SVGBackground';
import DeviceLogsViewer from '../../components/DeviceLogsViewer';
import { useTheme } from '../../context/ThemeContext';

export default function DeviceLogsScreen() {
  const { colors } = useTheme();
  return (
    <SVGBackground>
      <SafeAreaView style={styles.safe} edges={['top']}>
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          <Text style={[styles.title, { color: colors.text }]}>Device Logs</Text>
          <Text style={[styles.subtitle, { color: colors.textMuted }]}>Logs from this mobile app</Text>
          <DeviceLogsViewer />
        </ScrollView>
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: 20, paddingBottom: 120 },
  title: { fontSize: 28, fontWeight: '900', marginTop: 10, marginBottom: 4 },
  subtitle: { fontSize: 13, fontWeight: '500', marginBottom: 20 },
});
