import * as echoClient from '@/utils/echoClient'
import { logger } from '@/utils/logger'
import type { EchoChannelLike, EchoLike } from '@/ws/subscriptionTypes'

type SharedChannelType = 'private' | 'public'

interface SharedEchoChannelEntry {
  key: string
  channelName: string
  channelType: SharedChannelType
  owners: Set<string>
  echo: EchoLike | null
  channel: EchoChannelLike | null
}

const sharedEchoChannels = new Map<string, SharedEchoChannelEntry>()
let unsubscribeWsState: (() => void) | null = null

function getCurrentEcho(): EchoLike | null {
  return (
    echoClient.getEchoInstance?.() ||
    (typeof window !== 'undefined' ? window.Echo : null)
  ) as EchoLike | null
}

function getEntryKey(channelName: string, channelType: SharedChannelType): string {
  return `${channelType}:${channelName}`
}

function detachEntry(entry: SharedEchoChannelEntry, leaveChannel: boolean): void {
  if (leaveChannel && entry.channel) {
    try {
      entry.echo?.leave?.(entry.channelName)
    } catch (error) {
      logger.warn('[sharedEchoChannels] Failed to leave channel', {
        channel: entry.channelName,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  }

  entry.channel = null
  entry.echo = null
}

function attachEntry(entry: SharedEchoChannelEntry): EchoChannelLike | null {
  if (entry.owners.size === 0) {
    return null
  }

  const echo = getCurrentEcho()
  if (!echo) {
    logger.debug('[sharedEchoChannels] Echo not available, waiting for connect', {
      channel: entry.channelName,
    })
    return null
  }

  if (entry.channel && entry.echo === echo) {
    return entry.channel
  }

  if (entry.channel && entry.echo !== echo) {
    detachEntry(entry, false)
  }

  try {
    entry.channel =
      entry.channelType === 'private'
        ? echo.private(entry.channelName)
        : echo.channel(entry.channelName)
    entry.echo = echo
    return entry.channel
  } catch (error) {
    logger.warn('[sharedEchoChannels] Failed to attach channel', {
      channel: entry.channelName,
      error: error instanceof Error ? error.message : String(error),
    })
    detachEntry(entry, false)
    return null
  }
}

function ensureWsListener(): void {
  if (unsubscribeWsState) {
    return
  }

  unsubscribeWsState = echoClient.onWsStateChange((state) => {
    if (state === 'connected') {
      sharedEchoChannels.forEach((entry) => {
        attachEntry(entry)
      })
      return
    }

    if (state === 'disconnected' || state === 'unavailable' || state === 'failed') {
      sharedEchoChannels.forEach((entry) => {
        detachEntry(entry, false)
      })
    }
  })
}

function cleanupWsListenerIfIdle(): void {
  if (sharedEchoChannels.size > 0 || !unsubscribeWsState) {
    return
  }

  unsubscribeWsState()
  unsubscribeWsState = null
}

export function ensureOwnedSharedEchoChannel(
  channelName: string,
  channelType: SharedChannelType,
  ownerId: string
): EchoChannelLike | null {
  ensureWsListener()

  const key = getEntryKey(channelName, channelType)
  let entry = sharedEchoChannels.get(key)
  if (!entry) {
    entry = {
      key,
      channelName,
      channelType,
      owners: new Set<string>(),
      echo: null,
      channel: null,
    }
    sharedEchoChannels.set(key, entry)
  }

  entry.owners.add(ownerId)
  return attachEntry(entry)
}

export function releaseOwnedSharedEchoChannel(
  channelName: string,
  channelType: SharedChannelType,
  ownerId: string,
  leaveIfUnused = true
): void {
  const key = getEntryKey(channelName, channelType)
  const entry = sharedEchoChannels.get(key)
  if (!entry) {
    return
  }

  entry.owners.delete(ownerId)
  if (entry.owners.size > 0) {
    return
  }

  detachEntry(entry, leaveIfUnused)
  sharedEchoChannels.delete(key)
  cleanupWsListenerIfIdle()
}

export function detachSharedEchoChannel(
  channelName: string,
  channelType: SharedChannelType,
  leaveChannel = false
): void {
  const entry = sharedEchoChannels.get(getEntryKey(channelName, channelType))
  if (!entry) {
    return
  }

  detachEntry(entry, leaveChannel)
}

export function getSharedEchoChannel(
  channelName: string,
  channelType: SharedChannelType
): EchoChannelLike | null {
  return sharedEchoChannels.get(getEntryKey(channelName, channelType))?.channel ?? null
}

export function __resetSharedEchoChannelsForTests(): void {
  sharedEchoChannels.forEach((entry) => {
    detachEntry(entry, false)
  })
  sharedEchoChannels.clear()
  cleanupWsListenerIfIdle()
}
