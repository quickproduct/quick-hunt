import React, { useState } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';

interface TagInputProps {
  label: string;
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}

export default function TagInput({ label, tags, onChange, placeholder = 'Add...' }: TagInputProps) {
  const { colors } = useTheme();
  const [value, setValue] = useState('');

  function addTag() {
    const trimmed = value.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed]);
    }
    setValue('');
  }

  function removeTag(tag: string) {
    onChange(tags.filter((t) => t !== tag));
  }

  return (
    <View style={styles.container}>
      <Text style={[styles.label, { color: colors.textMuted }]}>{label.toUpperCase()}</Text>
      <View style={styles.tagsWrap}>
        {tags.map((tag) => (
          <View key={tag} style={[styles.tag, { backgroundColor: colors.primarySoft, borderColor: colors.border }]}>
            <Text style={[styles.tagText, { color: colors.primary }]} numberOfLines={1}>
              {tag}
            </Text>
            <Pressable onPress={() => removeTag(tag)} hitSlop={8}>
              <Ionicons name="close-circle" size={14} color={colors.primary} />
            </Pressable>
          </View>
        ))}
      </View>
      <View style={[styles.inputRow, { backgroundColor: colors.input, borderColor: colors.border }]}>
        <TextInput
          value={value}
          onChangeText={setValue}
          onSubmitEditing={addTag}
          placeholder={placeholder}
          placeholderTextColor={colors.textMuted}
          returnKeyType="done"
          style={[styles.input, { color: colors.text }]}
        />
        <Pressable onPress={addTag} disabled={!value.trim()} style={({ pressed }) => [{ opacity: pressed ? 0.6 : 1 }]}>
          <Ionicons name="add-circle" size={22} color={value.trim() ? colors.primary : colors.textMuted} />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginBottom: 16,
  },
  label: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0,
    marginBottom: 8,
  },
  tagsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginBottom: 8,
  },
  tag: {
    alignItems: 'center',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  tagText: {
    fontSize: 12,
    fontWeight: '700',
    maxWidth: 160,
  },
  inputRow: {
    alignItems: 'center',
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  input: {
    flex: 1,
    fontSize: 14,
    fontWeight: '700',
    height: 42,
  },
});
