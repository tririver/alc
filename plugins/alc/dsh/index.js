import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { startAcLlmBridge } from './llm-bridge.js'

export const name = 'alc-dsh'
export const inject = ['skills', 'llm', 'shellEnv']

const adapterDir = dirname(fileURLToPath(import.meta.url))
const skillDir = join(adapterDir, '..', 'skills', 'alc')
const skillPath = join(skillDir, 'SKILL.md')

function requiredFrontmatterField(frontmatter, key) {
  const value = new RegExp(`^${key}:\\s*(.+)$`, 'm')
    .exec(frontmatter)?.[1]
    ?.trim()
  if (value === undefined || value === '') {
    throw new Error(`ALC SKILL.md is missing ${key}`)
  }
  return value
}

function readAlcSkill() {
  const source = readFileSync(skillPath, 'utf8')
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/.exec(source)
  if (match === null) throw new Error('ALC SKILL.md is missing YAML frontmatter')
  const skill = {
    name: requiredFrontmatterField(match[1], 'name'),
    description: requiredFrontmatterField(match[1], 'description'),
    content: match[2],
  }
  if (skill.name !== 'alc') {
    throw new Error(`ALC SKILL.md declares unexpected name: ${skill.name}`)
  }
  return skill
}

export async function apply(ctx) {
  ctx.skills.register({
    ...readAlcSkill(),
    source: 'bundled',
    path: skillPath,
    resourceBase: { kind: 'directory', path: skillDir },
  })

  const bridge = startAcLlmBridge({ llm: ctx.llm })
  try {
    await bridge.ready
    ctx.shellEnv.register({
      name: 'alc-dsh',
      variables: {
        DSH_AC_LLM_SOCKET: {
          description: 'Unix socket used by ac-llm to call the native DSH model runtime.',
        },
        DSH_AC_LLM_TOKEN_FILE: {
          description: '0600 token file used to authenticate the AC LLM bridge.',
        },
        DSH_ALC_RUNTIME: {
          description: 'Absolute ALC runtime launcher path for DSH shell commands.',
        },
      },
      resolve() {
        return {
          DSH_AC_LLM_SOCKET: bridge.socketPath,
          DSH_AC_LLM_TOKEN_FILE: bridge.tokenPath,
          DSH_ALC_RUNTIME: join(skillDir, 'scripts', 'alc-runtime'),
        }
      },
    })
    ctx.effect(() => () => bridge.close(), 'alc-dsh:llm-bridge')
  } catch (error) {
    await bridge.close()
    throw error
  }
}
