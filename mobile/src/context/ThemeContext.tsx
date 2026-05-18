import React, { createContext, ReactNode, useContext, useEffect, useMemo, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useColorScheme } from 'react-native';
import { MD3DarkTheme, MD3LightTheme, type MD3Theme } from 'react-native-paper';

export type Theme = 'light' | 'dark' | 'system';
export type EffectiveTheme = 'light' | 'dark';

export interface ThemeColors {
  background: string;
  backgroundTop: string;
  backgroundBottom: string;
  surface: string;
  surfaceStrong: string;
  glass: string;
  glassStrong: string;
  text: string;
  textSecondary: string;
  textMuted: string;
  border: string;
  borderStrong: string;
  primary: string;
  primaryText: string;
  primarySoft: string;
  accentMint: string;
  accentAmber: string;
  accentCoral: string;
  success: string;
  warning: string;
  error: string;
  shadow: string;
  tabBar: string;
  input: string;
}

interface ThemeContextType {
  theme: Theme;
  effectiveTheme: EffectiveTheme;
  setTheme: (theme: Theme) => void;
  colors: ThemeColors;
  isDark: boolean;
  paperTheme: MD3Theme;
}

const lightColors: ThemeColors = {
  background: '#EDF4F7',
  backgroundTop: '#FFFFFF',
  backgroundBottom: '#DCE9EF',
  surface: 'rgba(255, 255, 255, 0.66)',
  surfaceStrong: '#FFFFFF',
  glass: 'rgba(255, 255, 255, 0.58)',
  glassStrong: 'rgba(255, 255, 255, 0.84)',
  text: '#07111F',
  textSecondary: '#3D4B60',
  textMuted: '#738398',
  border: 'rgba(255, 255, 255, 0.74)',
  borderStrong: 'rgba(80, 101, 127, 0.3)',
  primary: '#66E7FF',
  primaryText: '#031D27',
  primarySoft: 'rgba(102, 231, 255, 0.2)',
  accentMint: '#58F2A7',
  accentAmber: '#FFD166',
  accentCoral: '#FF7B6E',
  success: '#0FAD76',
  warning: '#A76A00',
  error: '#D64335',
  shadow: 'rgba(29, 49, 78, 0.24)',
  tabBar: 'rgba(255, 255, 255, 0.78)',
  input: 'rgba(255, 255, 255, 0.7)',
};

const darkColors: ThemeColors = {
  background: '#05070D',
  backgroundTop: '#121727',
  backgroundBottom: '#05070D',
  surface: 'rgba(16, 22, 34, 0.74)',
  surfaceStrong: '#111827',
  glass: 'rgba(23, 31, 48, 0.66)',
  glassStrong: 'rgba(32, 42, 62, 0.86)',
  text: '#F8FBFF',
  textSecondary: '#D5E0EF',
  textMuted: '#8FA1B8',
  border: 'rgba(255, 255, 255, 0.13)',
  borderStrong: 'rgba(255, 255, 255, 0.24)',
  primary: '#67E8F9',
  primaryText: '#031E2A',
  primarySoft: 'rgba(103, 232, 249, 0.16)',
  accentMint: '#5FF0B2',
  accentAmber: '#FAD36B',
  accentCoral: '#FF7A70',
  success: '#5FF0B2',
  warning: '#FAD36B',
  error: '#FF7A70',
  shadow: 'rgba(0, 0, 0, 0.62)',
  tabBar: 'rgba(11, 16, 26, 0.78)',
  input: 'rgba(19, 27, 43, 0.78)',
};

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const systemColorScheme = useColorScheme();
  const [theme, setThemeState] = useState<Theme>('system');

  useEffect(() => {
    const loadThemePreference = async () => {
      try {
        const savedTheme = await AsyncStorage.getItem('theme');
        if (savedTheme === 'light' || savedTheme === 'dark' || savedTheme === 'system') {
          setThemeState(savedTheme);
        }
      } catch (error) {
        console.error('Error loading theme preference:', error);
      }
    };

    void loadThemePreference();
  }, []);

  const effectiveTheme: EffectiveTheme =
    theme === 'system' ? (systemColorScheme === 'dark' ? 'dark' : 'light') : theme;

  const handleSetTheme = async (newTheme: Theme) => {
    setThemeState(newTheme);
    try {
      await AsyncStorage.setItem('theme', newTheme);
    } catch (error) {
      console.error('Error saving theme preference:', error);
    }
  };

  const value = useMemo(
    () => ({
      theme,
      effectiveTheme,
      setTheme: handleSetTheme,
      colors: effectiveTheme === 'dark' ? darkColors : lightColors,
      isDark: effectiveTheme === 'dark',
      paperTheme: {
        ...(effectiveTheme === 'dark' ? MD3DarkTheme : MD3LightTheme),
        roundness: 20,
        colors: {
          ...(effectiveTheme === 'dark' ? MD3DarkTheme.colors : MD3LightTheme.colors),
          primary: (effectiveTheme === 'dark' ? darkColors : lightColors).primary,
          onPrimary: (effectiveTheme === 'dark' ? darkColors : lightColors).primaryText,
          primaryContainer: (effectiveTheme === 'dark' ? darkColors : lightColors).primarySoft,
          onPrimaryContainer: (effectiveTheme === 'dark' ? darkColors : lightColors).text,
          secondary: (effectiveTheme === 'dark' ? darkColors : lightColors).accentAmber,
          tertiary: (effectiveTheme === 'dark' ? darkColors : lightColors).accentMint,
          background: (effectiveTheme === 'dark' ? darkColors : lightColors).background,
          surface: (effectiveTheme === 'dark' ? darkColors : lightColors).surfaceStrong,
          surfaceVariant: (effectiveTheme === 'dark' ? darkColors : lightColors).input,
          onSurface: (effectiveTheme === 'dark' ? darkColors : lightColors).text,
          onSurfaceVariant: (effectiveTheme === 'dark' ? darkColors : lightColors).textSecondary,
          outline: (effectiveTheme === 'dark' ? darkColors : lightColors).borderStrong,
          outlineVariant: (effectiveTheme === 'dark' ? darkColors : lightColors).border,
          error: (effectiveTheme === 'dark' ? darkColors : lightColors).error,
          onError: '#FFFFFF',
          errorContainer: effectiveTheme === 'dark' ? 'rgba(255,122,112,0.14)' : '#FFE5E1',
          onErrorContainer: (effectiveTheme === 'dark' ? darkColors : lightColors).error,
        },
      },
    }),
    [effectiveTheme, theme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
