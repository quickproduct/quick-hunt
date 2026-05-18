#!/usr/bin/env node

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const LOGS_DIR = path.join(__dirname, '../logs');
const PACKAGE = 'com.jobhunter.mobile';

// Ensure logs directory exists
if (!fs.existsSync(LOGS_DIR)) {
  fs.mkdirSync(LOGS_DIR, { recursive: true });
}

function getPlatform() {
  try {
    const devices = execSync('adb devices', { encoding: 'utf8' });
    if (devices.includes('\tdevice')) {
      return 'android';
    }
  } catch {
    // ADB not available or no devices
  }

  try {
    const devices = execSync('xcrun simctl list devices available', { encoding: 'utf8' });
    if (devices.includes('Booted')) {
      return 'ios';
    }
  } catch {
    // xcrun not available or no booted simulators
  }

  return null;
}

function pullAndroidLogs() {
  console.log('Pulling logs from Android device...');

  try {
    // Get the app's files directory
    const runCommand = `adb shell run-as ${PACKAGE} ls -la /data/data/${PACKAGE}/files/logs/`;
    execSync(runCommand, { stdio: 'inherit' });

    // Pull each log file
    const logFiles = ['info.log', 'warn.log', 'error.log', 'critical.log'];
    
    for (const logFile of logFiles) {
      const remotePath = `/data/data/${PACKAGE}/files/logs/${logFile}`;
      const localPath = path.join(LOGS_DIR, logFile);
      
      try {
        execSync(`adb shell run-as ${PACKAGE} cat ${remotePath} > ${localPath}`, { stdio: 'inherit' });
        console.log(`✓ Pulled ${logFile}`);
      } catch (error) {
        console.log(`✗ Failed to pull ${logFile} (may not exist yet)`);
      }
    }

    console.log('\nAndroid logs pulled successfully!');
  } catch (error) {
    console.error('Failed to pull Android logs:', error.message);
    console.log('\nNote: Make sure:');
    console.log('1. Device is connected via adb');
    console.log('2. App is debuggable (use --profile preview for EAS builds)');
    console.log('3. App has been run at least once to create log files');
    process.exit(1);
  }
}

function pullIosLogs() {
  console.log('Pulling logs from iOS simulator...');

  try {
    // Get the simulator UDID
    const devices = execSync('xcrun simctl list devices available', { encoding: 'utf8' });
    const lines = devices.split('\n');
    let udid = null;
    
    for (const line of lines) {
      if (line.includes('Booted')) {
        const match = line.match(/\(([A-F0-9-]+)\)/);
        if (match) {
          udid = match[1];
          break;
        }
      }
    }

    if (!udid) {
      throw new Error('No booted iOS simulator found');
    }

    console.log(`Using simulator UDID: ${udid}`);

    // Pull logs from simulator container
    const containerPath = execSync(
      `xcrun simctl get_app_container ${udid} ${PACKAGE} data`,
      { encoding: 'utf8' }
    ).trim();

    const logsPath = path.join(containerPath, 'logs');
    const logFiles = ['info.log', 'warn.log', 'error.log', 'critical.log'];

    for (const logFile of logFiles) {
      const remotePath = path.join(logsPath, logFile);
      const localPath = path.join(LOGS_DIR, logFile);
      
      try {
        const content = execSync(`xcrun simctl spawn ${udid} cat ${remotePath}`, { encoding: 'utf8' });
        fs.writeFileSync(localPath, content);
        console.log(`✓ Pulled ${logFile}`);
      } catch (error) {
        console.log(`✗ Failed to pull ${logFile} (may not exist yet)`);
      }
    }

    console.log('\niOS logs pulled successfully!');
  } catch (error) {
    console.error('Failed to pull iOS logs:', error.message);
    console.log('\nNote: Make sure:');
    console.log('1. iOS simulator is booted');
    console.log('2. App has been run at least once to create log files');
    process.exit(1);
  }
}

function main() {
  console.log('=== Mobile Log Puller ===\n');

  const platform = getPlatform();

  if (!platform) {
    console.error('No connected device or booted simulator found.');
    console.log('\nPlease connect an Android device via adb or boot an iOS simulator.');
    process.exit(1);
  }

  console.log(`Detected platform: ${platform}\n`);

  if (platform === 'android') {
    pullAndroidLogs();
  } else {
    pullIosLogs();
  }
}

main();
