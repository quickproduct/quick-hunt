import * as React from 'react';
import { Component, ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import SVGBackground from './SVGBackground';
import { logger } from '../utils/logger';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    logger.critical('ErrorBoundary caught an error', {
      error: error.message,
      componentStack: errorInfo.componentStack,
    }, error);
  }

  handleRetry = () => {
    logger.info('ErrorBoundary retry attempt');
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <SVGBackground>
          <View style={styles.container}>
            <View style={styles.card}>
              <View style={styles.icon}>
                <Ionicons name="alert-circle-outline" size={34} color="#FF7A70" />
              </View>
              <Text style={styles.title}>Something went wrong</Text>
              <Text style={styles.subtitle}>
                {this.state.error?.message || 'An unexpected error occurred'}
              </Text>
              <Pressable onPress={this.handleRetry} style={({ pressed }) => [styles.button, { opacity: pressed ? 0.82 : 1 }]}>
                <Text style={styles.buttonText}>Try Again</Text>
              </Pressable>
            </View>
          </View>
        </SVGBackground>
      );
    }

    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', flex: 1, justifyContent: 'center', padding: 22 },
  card: {
    alignItems: 'center',
    backgroundColor: 'rgba(17, 24, 39, 0.86)',
    borderColor: 'rgba(255,255,255,0.14)',
    borderRadius: 26,
    borderWidth: 1,
    padding: 26,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 18 },
    shadowOpacity: 0.5,
    shadowRadius: 30,
  },
  icon: {
    alignItems: 'center',
    backgroundColor: 'rgba(255,122,112,0.14)',
    borderRadius: 22,
    height: 64,
    justifyContent: 'center',
    marginBottom: 16,
    width: 64,
  },
  title: { color: '#F8FBFF', fontSize: 22, fontWeight: '900', marginBottom: 8, textAlign: 'center' },
  subtitle: { color: '#AEBED2', fontSize: 14, fontWeight: '700', lineHeight: 20, marginBottom: 22, textAlign: 'center' },
  button: { alignItems: 'center', backgroundColor: '#67E8F9', borderRadius: 18, minHeight: 50, justifyContent: 'center', paddingHorizontal: 22 },
  buttonText: { color: '#031E2A', fontSize: 14, fontWeight: '900' },
});
