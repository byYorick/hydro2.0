import { describe, expect, it } from 'vitest'
import {
  AUTHORITATIVE_EXTERNAL_GUIDES,
  AUTHORITATIVE_RUSSIAN_GUIDES,
  CROP_EC_PH_REFERENCE,
  KNOWLEDGE_TOPICS,
  LIBRARY_SECTION_TABS,
  topicsForLibrarySection,
  type LibrarySectionId,
} from '@/data/documentationKnowledgeLibrary'

describe('documentationKnowledgeLibrary', () => {
  it('имеет уникальные id тем и непустые источники с URL', () => {
    const ids = KNOWLEDGE_TOPICS.map(t => t.id)
    expect(new Set(ids).size).toBe(ids.length)

    for (const topic of KNOWLEDGE_TOPICS) {
      expect(topic.sortOrder).toBeGreaterThan(0)
      expect(topic.librarySection).toBeTruthy()
      expect(topic.sources.length).toBeGreaterThan(0)
      for (const s of topic.sources) {
        expect(s.url).toMatch(/^https?:\/\//)
        expect(s.label.length).toBeGreaterThan(3)
      }
    }
  })

  it('каждая вкладка библиотеки покрыта темами, кроме references (только справочники)', () => {
    const withTopics = new Set(KNOWLEDGE_TOPICS.map(t => t.librarySection))
    for (const tab of LIBRARY_SECTION_TABS) {
      if (tab.id === 'references') {
        continue
      }
      expect(withTopics.has(tab.id), `section ${tab.id} has no topics`).toBe(true)
    }
  })

  it('topicsForLibrarySection сортирует по sortOrder', () => {
    const sol = topicsForLibrarySection('solution')
    for (let i = 1; i < sol.length; i++) {
      expect(sol[i].sortOrder).toBeGreaterThanOrEqual(sol[i - 1].sortOrder)
    }
  })

  it('все темы попадают ровно в один известный раздел', () => {
    const allowed = new Set(LIBRARY_SECTION_TABS.map(t => t.id))
    for (const topic of KNOWLEDGE_TOPICS) {
      expect(allowed.has(topic.librarySection as LibrarySectionId)).toBe(true)
    }
  })

  it('справочник культур непустой и EC/pH заданы строками', () => {
    expect(CROP_EC_PH_REFERENCE.length).toBeGreaterThan(5)
    for (const row of CROP_EC_PH_REFERENCE) {
      expect(row.cropRu.length).toBeGreaterThan(1)
      expect(row.ecRange).toMatch(/\d/)
      expect(row.phRange).toMatch(/\d/)
    }
  })

  it('каталоги внешних ссылок содержат http(s)', () => {
    expect(AUTHORITATIVE_EXTERNAL_GUIDES.length).toBeGreaterThan(0)
    for (const g of AUTHORITATIVE_EXTERNAL_GUIDES) {
      expect(g.url).toMatch(/^https:\/\//)
    }
    expect(AUTHORITATIVE_RUSSIAN_GUIDES.length).toBeGreaterThan(0)
    for (const g of AUTHORITATIVE_RUSSIAN_GUIDES) {
      expect(g.url).toMatch(/^https?:\/\//)
    }
  })
})
