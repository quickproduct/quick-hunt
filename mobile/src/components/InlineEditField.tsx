import React, { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';

interface InlineEditFieldProps {
  label: string;
  value?: string | null;
  placeholder?: string;
  onSave: (value: string) => Promise<void>;
  keyboardType?: 'default' | 'email-address';
}

export default function InlineEditField({
  label,
  value,
  placeholder = 'Tap to edit...',
  onSave,
  keyboardType = 'default',
}: InlineEditFieldProps) {
  const { colors } = useTheme();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? '');
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await onSave(draft.trim());
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    setDraft(value ?? '');
    setEditing(false);
  }

  return (
    <View style={[styles.row, { borderBottomColor: colors.border }]}>
      <Text style={[styles.label, { color: colors.textMuted }]}>{label.toUpperCase()}</Text>
      {editing ? (
        <View style={styles.editRow}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder={placeholder}
            placeholderTextColor={colors.textMuted}
            keyboardType={keyboardType}
            autoFocus
            style={[styles.input, { color: colors.text, borderColor: colors.primary, backgroundColor: colors.input }]}
          />
          <View style={styles.actions}>
            {saving ? (
              <ActivityIndicator size="small" color={colors.primary} />
            ) : (
              <>
                <Pressable onPress={handleSave} hitSlop={8}>
                  <Ionicons name="checkmark-circle" size={22} color={colors.success} />
                </Pressable>
                <Pressable onPress={handleCancel} hitSlop={8}>
                  <Ionicons name="close-circle" size={22} color={colors.error} />
                </Pressable>
              </>
            )}
          </View>
        </View>
      ) : (
        <Pressable onPress={() => { setDraft(value ?? ''); setEditing(true); }} style={styles.displayRow}>
          <Text style={[styles.displayValue, { color: value ? colors.text : colors.textMuted }]} numberOfLines={1}>
            {value || placeholder}
          </Text>
          <Ionicons name="pencil-outline" size={14} color={colors.textMuted} />
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    paddingVertical: 10,
  },
  label: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  editRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  input: {
    borderRadius: 14,
    borderWidth: 1,
    flex: 1,
    fontSize: 14,
    fontWeight: '700',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  actions: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  displayRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    minHeight: 34,
  },
  displayValue: {
    flex: 1,
    fontSize: 14,
    fontWeight: '700',
  },
});
