import { create } from 'zustand'
import { on } from '../api/ws'

export interface FixtureColor {
  id: string
  idx: number
  r: number; g: number; b: number
  parked: boolean
  x: number; y: number
  address: number
  traverse: string | null
  snap_point: number | null
  values: Record<string, number>
}

export interface EventDef {
  name: string
  type: string
  active: boolean
  data?: Record<string, unknown>
}

interface EngineStore {
  masterDimmer: number
  parkedFixtures: number[]
  fixtureColors: FixtureColor[]
  activeOverlays: string[]
  events: EventDef[]
  setMasterDimmer: (v: number) => void
  setFixtureColors: (f: FixtureColor[]) => void
  setActiveOverlays: (o: string[]) => void
  setEvents: (e: EventDef[]) => void
  setParked: (p: number[]) => void
}

export const useEngineStore = create<EngineStore>((set) => ({
  masterDimmer:   1.0,
  parkedFixtures: [],
  fixtureColors:  [],
  activeOverlays: [],
  events:         [],

  setMasterDimmer:  (v) => set({ masterDimmer: v }),
  setFixtureColors: (f) => set({ fixtureColors: f }),
  setActiveOverlays:(o) => set({ activeOverlays: o }),
  setEvents:        (e) => set({ events: e }),
  setParked:        (p) => set({ parkedFixtures: p }),
}))

// Wire WebSocket messages to store
on('fixture_colors', (p) => useEngineStore.getState().setFixtureColors(p as FixtureColor[]))
on('active_overlays', (p) => useEngineStore.getState().setActiveOverlays(p as string[]))
on('events_state', (p) => useEngineStore.getState().setEvents(p as EventDef[]))
on('engine_meta', (p: unknown) => {
  const meta = p as { master_dimmer: number; parked_fixtures: number[] }
  useEngineStore.getState().setMasterDimmer(meta.master_dimmer)
  useEngineStore.getState().setParked(meta.parked_fixtures)
})
