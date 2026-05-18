import React, { useEffect, Suspense, lazy } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { BlurView } from 'expo-blur';
import { useAuthStore } from '../store/authStore';
import { useTheme } from '../context/ThemeContext';
import { useJobsStore, DEFAULT_FILTERS } from '../store/jobsStore';
import LoginScreen from '../screens/auth/LoginScreen';
import RegisterScreen from '../screens/auth/RegisterScreen';
import LoadingScreen from '../screens/common/LoadingScreen';
import { Ionicons } from '@expo/vector-icons';

// Auth screens
const ForgotPasswordScreen = lazy(() => import('../screens/auth/ForgotPasswordScreen'));

// Main tab screens
const DashboardScreen = lazy(() => import('../screens/dashboard/DashboardScreen'));
const JobsScreen = lazy(() => import('../screens/jobs/JobsScreen'));
const JobDetailScreen = lazy(() => import('../screens/jobs/JobDetailScreen'));
const SearchScreen = lazy(() => import('../screens/search/SearchScreen'));
const CandidatesScreen = lazy(() => import('../screens/candidates/CandidatesScreen'));
const CandidateEditScreen = lazy(() => import('../screens/candidates/CandidateEditScreen'));

// More stack screens
const MoreMenuScreen = lazy(() => import('../screens/more/MoreMenuScreen'));
const LogsScreen = lazy(() => import('../screens/logs/LogsScreen'));
const DirectSendScreen = lazy(() => import('../screens/direct-send/DirectSendScreen'));
const BlacklistScreen = lazy(() => import('../screens/blacklist/BlacklistScreen'));
const ProfileScreen = lazy(() => import('../screens/profile/ProfileScreen'));
const SettingsScreen = lazy(() => import('../screens/settings/SettingsScreen'));
const BillingScreen = lazy(() => import('../screens/billing/BillingScreen'));
const AdminScreen = lazy(() => import('../screens/admin/AdminScreen'));
const CronMonitorScreen = lazy(() => import('../screens/admin/CronMonitorScreen'));
const CronRunDetailScreen = lazy(() => import('../screens/admin/CronRunDetailScreen'));
const AdminQuotaScreen = lazy(() => import('../screens/admin/AdminQuotaScreen'));
const DeviceLogsScreen = lazy(() => import('../screens/admin/DeviceLogsScreen'));
const OnboardingScreen = lazy(() => import('../screens/onboarding/OnboardingScreen'));

function LoadingFallback() {
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background }}>
      <ActivityIndicator size="large" color={colors.primary} />
    </View>
  );
}

function S({ screen: Screen }: { screen: React.ComponentType }) {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <Screen />
    </Suspense>
  );
}

export type RootStackParamList = {
  Auth: undefined;
  Onboarding: undefined;
  Main: undefined;
};

export type AuthStackParamList = {
  Login: undefined;
  Register: undefined;
  ForgotPassword: undefined;
};

export type MainTabParamList = {
  Dashboard: undefined;
  Jobs: undefined;
  Candidates: undefined;
  Search: undefined;
  More: undefined;
};

export type JobsStackParamList = {
  JobsList: undefined;
  JobDetail: { jobId: string };
};

export type CandidatesStackParamList = {
  CandidatesList: undefined;
  CandidateEdit: { candidateId?: string };
};

export type MoreStackParamList = {
  MoreMenu: undefined;
  Logs: undefined;
  DirectSend: undefined;
  Blacklist: undefined;
  Profile: undefined;
  Settings: undefined;
  Billing: undefined;
  Admin: undefined;
  CronMonitor: undefined;
  CronRunDetail: { runId: string };
  AdminQuota: undefined;
  DeviceLogs: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const MainTab = createBottomTabNavigator<MainTabParamList>();
const JobsStack = createNativeStackNavigator<JobsStackParamList>();
const CandidatesStack = createNativeStackNavigator<CandidatesStackParamList>();
const MoreStack = createNativeStackNavigator<MoreStackParamList>();

function sharedHeaderOptions(colors: ReturnType<typeof useTheme>['colors']) {
  return {
    headerStyle: { backgroundColor: colors.surfaceStrong },
    headerTransparent: false,
    headerShadowVisible: false,
    headerTintColor: colors.text,
    headerTitleStyle: { color: colors.text, fontWeight: '900' as const, fontSize: 17 },
    headerBackTitleVisible: false,
    contentStyle: { backgroundColor: colors.background },
    animation: 'simple_push' as const,
  };
}

function AuthNavigator() {
  const { colors } = useTheme();
  return (
    <AuthStack.Navigator screenOptions={sharedHeaderOptions(colors)}>
      <AuthStack.Screen name="Login" component={LoginScreen} options={{ title: 'Welcome Back', headerShown: false }} />
      <AuthStack.Screen name="Register" component={RegisterScreen} options={{ title: 'Create Account', headerShown: false }} />
      <AuthStack.Screen name="ForgotPassword" options={{ title: 'Reset Password' }}>
        {() => <S screen={ForgotPasswordScreen} />}
      </AuthStack.Screen>
    </AuthStack.Navigator>
  );
}

function JobsNavigator() {
  const { colors } = useTheme();
  return (
    <JobsStack.Navigator screenOptions={sharedHeaderOptions(colors)}>
      <JobsStack.Screen name="JobsList" options={{ title: 'Jobs', headerShown: false }}>
        {() => <S screen={JobsScreen} />}
      </JobsStack.Screen>
      <JobsStack.Screen name="JobDetail" options={{ title: 'Job Details' }}>
        {() => <S screen={JobDetailScreen} />}
      </JobsStack.Screen>
    </JobsStack.Navigator>
  );
}

function CandidatesNavigator() {
  const { colors } = useTheme();
  return (
    <CandidatesStack.Navigator screenOptions={sharedHeaderOptions(colors)}>
      <CandidatesStack.Screen name="CandidatesList" options={{ title: 'Candidates', headerShown: false }}>
        {() => <S screen={CandidatesScreen} />}
      </CandidatesStack.Screen>
      <CandidatesStack.Screen name="CandidateEdit" options={{ title: 'Edit Candidate' }}>
        {() => <S screen={CandidateEditScreen} />}
      </CandidatesStack.Screen>
    </CandidatesStack.Navigator>
  );
}

function MoreNavigator() {
  const { colors } = useTheme();
  return (
    <MoreStack.Navigator screenOptions={sharedHeaderOptions(colors)}>
      <MoreStack.Screen name="MoreMenu" options={{ title: 'More', headerShown: false }}>
        {() => <S screen={MoreMenuScreen} />}
      </MoreStack.Screen>
      <MoreStack.Screen name="Logs" options={{ title: 'Send Logs' }}>
        {() => <S screen={LogsScreen} />}
      </MoreStack.Screen>
      <MoreStack.Screen name="DirectSend" options={{ title: 'Direct HR Send' }}>
        {() => <S screen={DirectSendScreen} />}
      </MoreStack.Screen>
      <MoreStack.Screen name="Blacklist" options={{ title: 'Company Blacklist' }}>
        {() => <S screen={BlacklistScreen} />}
      </MoreStack.Screen>
      <MoreStack.Screen name="Profile" options={{ title: 'Profile' }}>
        {() => <S screen={ProfileScreen} />}
      </MoreStack.Screen>
      <MoreStack.Screen name="Settings" options={{ title: 'Settings' }}>
        {() => <S screen={SettingsScreen} />}
      </MoreStack.Screen>
      <MoreStack.Screen name="Billing" options={{ title: 'Billing' }}>
        {() => <S screen={BillingScreen} />}
      </MoreStack.Screen>
      <MoreStack.Screen name="Admin" options={{ title: 'Admin Panel' }}>
        {() => <S screen={AdminScreen} />}
      </MoreStack.Screen>
      <MoreStack.Screen name="CronMonitor" options={{ title: 'Cron Monitor' }}>
        {() => <S screen={CronMonitorScreen} />}
      </MoreStack.Screen>
      <MoreStack.Screen name="CronRunDetail" options={{ title: 'Run Detail' }}>
        {() => <S screen={CronRunDetailScreen} />}
      </MoreStack.Screen>
      <MoreStack.Screen name="AdminQuota" options={{ title: 'API Quotas' }}>
        {() => <S screen={AdminQuotaScreen} />}
      </MoreStack.Screen>
      <MoreStack.Screen name="DeviceLogs" options={{ title: 'Device Logs' }}>
        {() => <S screen={DeviceLogsScreen} />}
      </MoreStack.Screen>
    </MoreStack.Navigator>
  );
}

function countActiveFilters(filters: typeof DEFAULT_FILTERS): number {
  let count = 0;
  if (filters.status) count++;
  if (filters.portal) count++;
  if (filters.job_type) count++;
  if (filters.has_hr_email) count++;
  if (filters.has_cover) count++;
  if (filters.min_score > 0) count++;
  if (filters.scraped_after) count++;
  if (filters.posted_after) count++;
  if (filters.search) count++;
  if (filters.sort_by !== DEFAULT_FILTERS.sort_by || filters.sort_dir !== DEFAULT_FILTERS.sort_dir) count++;
  return count;
}

function MainTabNavigator() {
  const { colors, isDark } = useTheme();
  const { filters } = useJobsStore();
  const activeJobFilters = countActiveFilters(filters);

  return (
    <MainTab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          const icons: Record<string, [keyof typeof Ionicons.glyphMap, keyof typeof Ionicons.glyphMap]> = {
            Dashboard: ['grid', 'grid-outline'],
            Jobs: ['briefcase', 'briefcase-outline'],
            Candidates: ['people', 'people-outline'],
            Search: ['search', 'search-outline'],
            More: ['ellipsis-horizontal-circle', 'ellipsis-horizontal-circle-outline'],
          };
          const [active, inactive] = icons[route.name] ?? ['grid', 'grid-outline'];
          return (
            <View
              style={[
                styles.tabIconWrap,
                focused && {
                  backgroundColor: colors.primarySoft,
                  borderColor: colors.border,
                },
              ]}
            >
              <Ionicons name={focused ? active : inactive} size={focused ? size + 1 : size} color={color} />
            </View>
          );
        },
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarStyle: {
          backgroundColor: colors.tabBar,
          borderColor: colors.border,
          borderRadius: 24,
          borderTopWidth: 1,
          borderWidth: 1,
          bottom: 10,
          height: 70,
          left: 12,
          paddingBottom: 8,
          paddingTop: 6,
          position: 'absolute',
          right: 12,
          elevation: 0,
          shadowColor: colors.shadow,
          shadowOpacity: isDark ? 0.52 : 0.2,
          shadowRadius: 24,
          shadowOffset: { width: 0, height: 12 },
        },
        tabBarItemStyle: {
          borderRadius: 18,
          marginHorizontal: 0,
        },
        tabBarBackground: () => (
          <BlurView
            intensity={isDark ? 42 : 58}
            tint={isDark ? 'dark' : 'light'}
            style={StyleSheet.absoluteFill}
          />
        ),
        tabBarLabelStyle: { fontSize: 10, fontWeight: '800', marginTop: -1 },
      })}
    >
      <MainTab.Screen name="Dashboard">
        {() => <S screen={DashboardScreen} />}
      </MainTab.Screen>
      <MainTab.Screen
        name="Jobs"
        component={JobsNavigator}
        options={{
          headerShown: false,
          tabBarBadge: activeJobFilters > 0 ? activeJobFilters : undefined,
          tabBarBadgeStyle: { backgroundColor: colors.primary, fontSize: 10 },
        }}
      />
      <MainTab.Screen name="Candidates" component={CandidatesNavigator} options={{ headerShown: false }} />
      <MainTab.Screen name="Search">
        {() => <S screen={SearchScreen} />}
      </MainTab.Screen>
      <MainTab.Screen name="More" component={MoreNavigator} options={{ headerShown: false }} />
    </MainTab.Navigator>
  );
}

const styles = StyleSheet.create({
  tabIconWrap: {
    alignItems: 'center',
    borderColor: 'transparent',
    borderRadius: 14,
    borderWidth: 1,
    height: 32,
    justifyContent: 'center',
    marginBottom: -1,
    width: 38,
  },
});

export default function AppNavigator() {
  const { isAuthenticated, isLoading, loadStoredAuth } = useAuthStore();
  const { colors, effectiveTheme } = useTheme();

  useEffect(() => {
    void loadStoredAuth();
  }, [loadStoredAuth]);

  if (isLoading) return <LoadingScreen />;

  return (
    <NavigationContainer
      theme={{
        dark: effectiveTheme === 'dark',
        colors: {
          primary: colors.primary,
          background: colors.background,
          card: colors.surfaceStrong,
          text: colors.text,
          border: colors.border,
          notification: colors.accentCoral,
        },
      }}
    >
      <StatusBar style={effectiveTheme === 'dark' ? 'light' : 'dark'} />
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {isAuthenticated ? (
          <>
            <Stack.Screen name="Main" component={MainTabNavigator} />
            <Stack.Screen name="Onboarding">
              {() => <S screen={OnboardingScreen} />}
            </Stack.Screen>
          </>
        ) : (
          <Stack.Screen name="Auth" component={AuthNavigator} />
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
