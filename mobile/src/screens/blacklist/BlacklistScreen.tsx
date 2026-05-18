import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, EmptyState, GlassCard, ScreenError, SectionHeader } from '../../components/GlassKit';
import InlineEditField from '../../components/InlineEditField';
import { useTheme } from '../../context/ThemeContext';
import { useBlacklistStore } from '../../store/blacklistStore';
import { BlacklistedCompany } from '../../types';

function BlacklistItem({ item }: { item: BlacklistedCompany }) {
  const { colors } = useTheme();
  const { updateEntry, removeEntry } = useBlacklistStore();

  function confirmDelete() {
    Alert.alert('Remove', `Remove "${item.name}" from blacklist?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: () => void removeEntry(item.id) },
    ]);
  }

  return (
    <GlassCard style={styles.itemCard}>
      <View style={styles.itemHeader}>
        <Text style={[styles.company, { color: colors.text }]}>{item.name}</Text>
        <Pressable onPress={confirmDelete} hitSlop={8}>
          <Ionicons name="trash-outline" size={18} color={colors.error} />
        </Pressable>
      </View>
      <InlineEditField
        label="Reason"
        value={item.reason}
        placeholder="No reason given"
        onSave={(v) => updateEntry(item.id, v)}
      />
      <Text style={[styles.date, { color: colors.textMuted }]}>
        Added {new Date(item.created_at).toLocaleDateString()}
      </Text>
    </GlassCard>
  );
}

export default function BlacklistScreen() {
  const { colors } = useTheme();
  const { items, loading, error, fetchBlacklist, addToBlacklist } = useBlacklistStore();

  const [search, setSearch] = useState('');
  const [newName, setNewName] = useState('');
  const [newReason, setNewReason] = useState('');
  const [adding, setAdding] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    void fetchBlacklist();
  }, [fetchBlacklist]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchBlacklist();
    setRefreshing(false);
  }, [fetchBlacklist]);

  async function handleAdd() {
    if (!newName.trim()) {
      Alert.alert('Error', 'Company name is required');
      return;
    }
    setAdding(true);
    try {
      await addToBlacklist(newName.trim(), newReason.trim() || undefined);
      setNewName('');
      setNewReason('');
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to add company');
    } finally {
      setAdding(false);
    }
  }

  const filtered = items.filter(
    (item) =>
      item.name.toLowerCase().includes(search.toLowerCase()) ||
      (item.reason ?? '').toLowerCase().includes(search.toLowerCase())
  );

  if (loading && !refreshing && items.length === 0) {
    return (
      <SVGBackground>
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} size="large" />
        </View>
      </SVGBackground>
    );
  }

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <FlatList
          data={filtered}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          ListHeaderComponent={
            <>
              <Text style={[styles.title, { color: colors.text }]}>Company Blacklist</Text>
              <Text style={[styles.subtitle, { color: colors.textMuted }]}>
                Companies excluded from scraping and emailing
              </Text>

              {/* Search */}
              <View style={[styles.searchBar, { backgroundColor: colors.input, borderColor: colors.border }]}>
                <Ionicons name="search-outline" size={16} color={colors.textMuted} />
                <TextInput
                  value={search}
                  onChangeText={setSearch}
                  placeholder="Search by name or reason..."
                  placeholderTextColor={colors.textMuted}
                  style={[styles.searchInput, { color: colors.text }]}
                />
              </View>

              {/* Add form */}
              <SectionHeader title="Add Company" />
              <GlassCard>
                <TextInput
                  value={newName}
                  onChangeText={setNewName}
                  placeholder="Company name (required)"
                  placeholderTextColor={colors.textMuted}
                  style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                />
                <TextInput
                  value={newReason}
                  onChangeText={setNewReason}
                  placeholder="Reason (optional)"
                  placeholderTextColor={colors.textMuted}
                  style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                />
                <AppButton label={adding ? 'Adding...' : 'Add to Blacklist'} icon="ban-outline" onPress={handleAdd} loading={adding} disabled={!newName.trim()} />
              </GlassCard>

              {error && <ScreenError message={error} onRetry={() => void fetchBlacklist()} />}

              <SectionHeader title={`Blacklisted (${filtered.length})`} />
            </>
          }
          renderItem={({ item }) => <BlacklistItem item={item} />}
          ListEmptyComponent={
            !loading ? (
              <EmptyState icon="ban-outline" title="No companies blacklisted" message="Add companies you want to exclude from job scraping." />
            ) : null
          }
          ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
        />
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  center: { alignItems: 'center', flex: 1, justifyContent: 'center' },
  content: { padding: 20, paddingBottom: 118 },
  title: { fontSize: 28, fontWeight: '900', marginTop: 10 },
  subtitle: { fontSize: 13, fontWeight: '500', lineHeight: 18, marginBottom: 16, marginTop: 4 },
  searchBar: { alignItems: 'center', borderRadius: 18, borderWidth: 1, flexDirection: 'row', gap: 8, marginBottom: 20, minHeight: 50, paddingHorizontal: 14, paddingVertical: 10 },
  searchInput: { flex: 1, fontSize: 14, fontWeight: '700' },
  input: { borderRadius: 17, borderWidth: 1, fontSize: 14, fontWeight: '700', marginBottom: 10, paddingHorizontal: 14, paddingVertical: 13 },
  itemCard: { padding: 14 },
  itemHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  company: { flex: 1, fontSize: 15, fontWeight: '800' },
  date: { fontSize: 11, fontWeight: '600', marginTop: 6 },
});
