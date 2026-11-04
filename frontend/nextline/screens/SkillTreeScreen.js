// The skill tree: branches in lanes, prerequisite lines, and what to work on next. Scrolls sideways through the
// tree; pinch to zoom on iPhone.
import { useCallback, useMemo, useRef, useState } from 'react';
import { Platform, ScrollView, StyleSheet, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import Svg, { Path } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import LevelBar from '../components/LevelBar';
import { ErrorState, Header, Loading } from '../components/ui';
import { NODE_H, NODE_W, layoutTree, nodeCaption, scrollTargetFor } from '../utils/skillTree';
import { SKILL_STATE, colors, fonts, ui } from '../theme';

function SkillNode({ skill, node, highlighted, onPress }) {
  const s = SKILL_STATE[skill.state];
  const mastered = skill.state === 'mastered';
  const locked = skill.state === 'locked';
  return (
    <TouchableOpacity
      onPress={onPress}
      accessibilityLabel={`${skill.name}, ${s.label}`}
      style={[
        styles.node,
        { left: node.x, top: node.y },
        mastered && { backgroundColor: colors.accent, borderColor: colors.accent },
        skill.state === 'in_progress' && { borderColor: colors.accent, borderWidth: 2 },
        skill.state === 'ready' && { borderColor: colors.text },
        locked && { opacity: 0.55 },
        highlighted && styles.highlight,
      ]}
    >
      <View style={ui.between}>
        <Text style={[styles.nodeName, mastered && { color: colors.bg }]} numberOfLines={2}>{skill.name}</Text>
        <Ionicons name={s.icon} size={16} color={mastered ? colors.bg : s.color} />
      </View>
      <Text style={[styles.nodeCaption, mastered && { color: colors.bg }]} numberOfLines={1}>{nodeCaption(skill)}</Text>
    </TouchableOpacity>
  );
}

export default function SkillTreeScreen() {
  const navigation = useNavigation();
  const { logout } = useAuth();
  const { width: screenWidth } = useWindowDimensions();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [focus, setFocus] = useState(null);
  const treeScroll = useRef(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await fetchJson('/api/skills/', { logout }));
    } catch (err) {
      setError(err.message);
    }
  }, [logout]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const layout = useMemo(() => data && layoutTree(data.branches, data.skills), [data]);

  if (error && !data) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <Loading />;

  const byId = Object.fromEntries(data.skills.map((s) => [s.id, s]));
  const openSkill = (id) => navigation.navigate('Skill', { id });
  const showInTree = (id) => {
    setFocus(id);
    treeScroll.current?.scrollTo({ x: scrollTargetFor(layout.nodes[id], screenWidth), animated: true });
  };

  return (
    <ScrollView contentContainerStyle={[ui.scroll, { paddingHorizontal: 0 }]}>
      <View style={{ paddingHorizontal: 20, gap: 14 }}>
        <Header caption="Skills" back={false} />
        <Text style={ui.title}>Skill tree</Text>
        <View style={ui.card}>
          <LevelBar level={data.level} streakWeeks={data.streak_weeks} />
          <Text style={ui.small}>{data.mastered_count} of {data.skills.length} skills mastered</Text>
        </View>

        {data.next_up.length > 0 && (
          <View style={{ gap: 8 }}>
            <Text style={ui.label}>Next up</Text>
            {data.next_up.map((id) => {
              const s = byId[id];
              return (
                <TouchableOpacity key={id} style={[ui.card, styles.nextUp]} onPress={() => openSkill(id)}
                  onLongPress={() => showInTree(id)}>
                  <Ionicons name={SKILL_STATE[s.state].icon} size={22} color={colors.accent} />
                  <View style={{ flex: 1 }}>
                    <Text style={ui.strong}>{s.name}</Text>
                    <Text style={ui.small} numberOfLines={1}>
                      {s.state === 'in_progress'
                        ? (s.missing.length ? `Needs ${s.missing.join(', ')}` : 'Ready for the mastery test')
                        : s.description}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                </TouchableOpacity>
              );
            })}
          </View>
        )}

        <View style={styles.legend}>
          {Object.entries(SKILL_STATE).map(([key, s]) => (
            <View key={key} style={ui.row}>
              <Ionicons name={s.icon} size={14} color={s.color} />
              <Text style={ui.small}>{s.label}</Text>
            </View>
          ))}
        </View>
      </View>

      <ScrollView
        ref={treeScroll}
        horizontal
        showsHorizontalScrollIndicator={false}
        maximumZoomScale={Platform.OS === 'ios' ? 2 : 1}
        minimumZoomScale={Platform.OS === 'ios' ? 0.6 : 1}
        contentContainerStyle={{ paddingHorizontal: 4 }}
      >
        <View style={{ width: layout.width, height: layout.height }}>
          {layout.lanes.map((lane) => (
            <View key={lane.id} style={[styles.laneLabel, { top: lane.y }]}>
              <View style={[styles.laneDot, { backgroundColor: lane.color }]} />
              <Text style={ui.label}>{lane.name}</Text>
            </View>
          ))}
          <Svg width={layout.width} height={layout.height} style={StyleSheet.absoluteFill}>
            {layout.edges.map((e) => (
              <Path
                key={`${e.from}-${e.to}`}
                d={e.path}
                stroke={e.met ? colors.accent : colors.borderDashed}
                strokeWidth={e.met ? 2.5 : 1.5}
                strokeDasharray={e.met ? undefined : '5,4'}
                fill="none"
              />
            ))}
          </Svg>
          {data.skills.map((s) => (
            <SkillNode key={s.id} skill={s} node={layout.nodes[s.id]} highlighted={focus === s.id}
              onPress={() => openSkill(s.id)} />
          ))}
        </View>
      </ScrollView>
      <Text style={[ui.small, { paddingHorizontal: 20 }]}>
        Swipe sideways to see the whole tree{Platform.OS === 'ios' ? ', pinch to zoom' : ''}. Hold a Next up skill to find it.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  node: {
    position: 'absolute', width: NODE_W, height: NODE_H, borderRadius: 12, padding: 9, justifyContent: 'space-between',
    backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
  },
  highlight: { shadowColor: colors.accent, shadowOpacity: 0.9, shadowRadius: 10, elevation: 8, borderColor: colors.accent },
  nodeName: { flex: 1, fontFamily: fonts.semibold, fontSize: 14, lineHeight: 17, color: colors.text, marginRight: 4 },
  nodeCaption: { fontFamily: fonts.regular, fontSize: 12, color: colors.muted },
  laneLabel: { position: 'absolute', left: 16, flexDirection: 'row', alignItems: 'center', gap: 6 },
  laneDot: { width: 8, height: 8, borderRadius: 4 },
  nextUp: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
});
