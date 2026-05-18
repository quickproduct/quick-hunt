module.exports = function(api) {
  api.cache(true);
  return {
    presets: [
      ['babel-preset-expo', {
        jsxImportSource: undefined,
        loose: false,
        useBuiltIns: true,
        corejs: 3,
      }],
    ],
    plugins: [
      // Required for React Native Paper
      'react-native-paper/babel',
    ],
  };
};
