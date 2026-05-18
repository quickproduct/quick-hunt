import React, { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { PaperProvider } from 'react-native-paper';
import AppNavigator from './src/navigation/AppNavigator';
import { ErrorBoundary } from './src/components/ErrorBoundary';
import { ThemeProvider, useTheme } from './src/context/ThemeContext';
import { installGlobalErrorHandler } from './src/utils/logger';

function ThemedAppShell() {
  const { paperTheme } = useTheme();

  return (
    <PaperProvider theme={paperTheme}>
      <ErrorBoundary>
        <AppNavigator />
      </ErrorBoundary>
    </PaperProvider>
  );
}

export default function App() {
  useEffect(() => {
    // Install global unhandled exception → CRITICAL log capture
    installGlobalErrorHandler();
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <ThemeProvider>
          <ThemedAppShell />
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
