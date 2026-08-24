import { router } from 'expo-router';
import { Tabs } from 'expo-router/tabs';
import { Pressable, type ColorValue } from 'react-native';
import { SymbolView } from 'expo-symbols';

import { useTheme } from '@/hooks/use-theme';

function TabIcon({ name, color }: { name: 'tray.full' | 'plus.circle' | 'checkmark.circle'; color: ColorValue }) {
  return <SymbolView name={name} size={24} tintColor={color} />;
}

function SettingsButton() {
  const theme = useTheme();
  return (
    <Pressable onPress={() => router.push('/settings')} hitSlop={12} style={{ marginRight: 4 }}>
      <SymbolView name="gearshape" size={20} tintColor={theme.text} />
    </Pressable>
  );
}

export default function TabsLayout() {
  return (
    <Tabs>
      <Tabs.Screen
        name="index"
        options={{
          title: 'Slip Box',
          tabBarIcon: ({ color }) => <TabIcon name="tray.full" color={color} />,
          headerRight: () => <SettingsButton />,
        }}
      />
      <Tabs.Screen
        name="submit"
        options={{
          title: 'Add Source',
          tabBarIcon: ({ color }) => <TabIcon name="plus.circle" color={color} />,
        }}
      />
      <Tabs.Screen
        name="review"
        options={{
          title: 'Review',
          tabBarIcon: ({ color }) => <TabIcon name="checkmark.circle" color={color} />,
        }}
      />
    </Tabs>
  );
}
