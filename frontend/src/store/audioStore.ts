import { create } from 'zustand'
import { on } from '../api/ws'

interface AudioLiveState {
  is_listening: boolean
  beat_triggered: boolean
  beat_index: number
  level: number
  phase: string
  volume: number
  ml_active: boolean
}

interface AudioFileState {
  is_playing: boolean
  bpm: number
  last_state: string
  current_beat_idx: number
  file_path: string
}

interface PlaySettings {
  source_mode: string
  mode: string
  selected_bank: string | null
  flash_automatik: boolean
  is_active: boolean
  custom_timeline: Record<string, string[]>
}

interface AudioStore {
  live: AudioLiveState
  file: AudioFileState
  playSettings: PlaySettings
  magicAuto: Record<string, unknown>
  setLive: (s: AudioLiveState) => void
  setFile: (s: AudioFileState) => void
  setPlaySettings: (s: PlaySettings) => void
  setMagicAuto: (s: Record<string, unknown>) => void
}

const defaultLive: AudioLiveState = {
  is_listening: false, beat_triggered: false, beat_index: 0,
  level: 0, phase: 'WAITING', volume: 0, ml_active: false,
}
const defaultFile: AudioFileState = {
  is_playing: false, bpm: 0, last_state: 'BREAK',
  current_beat_idx: 0, file_path: '',
}
const defaultPlaySettings: PlaySettings = {
  source_mode: 'MP3', mode: 'Scene Sync', selected_bank: null,
  flash_automatik: true, is_active: false,
  custom_timeline: { BREAK: [], BUILDUP: [], DROP: [] },
}

export const useAudioStore = create<AudioStore>((set) => ({
  live: defaultLive,
  file: defaultFile,
  playSettings: defaultPlaySettings,
  magicAuto: {},
  setLive:         (s) => set({ live: s }),
  setFile:         (s) => set({ file: s }),
  setPlaySettings: (s) => set({ playSettings: s }),
  setMagicAuto:    (s) => set({ magicAuto: s }),
}))

on('audio_live',    (p) => useAudioStore.getState().setLive(p as AudioLiveState))
on('audio_file',    (p) => useAudioStore.getState().setFile(p as AudioFileState))
on('play_settings', (p) => useAudioStore.getState().setPlaySettings(p as PlaySettings))
on('magic_auto',    (p) => useAudioStore.getState().setMagicAuto(p as Record<string, unknown>))
