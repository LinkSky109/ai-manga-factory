import { useDeferredValue, useState } from "react";

import { SectionCard } from "../../components/stitch/SectionCard";
import { StatusPill } from "../../components/stitch/StatusPill";
import type { CharacterProfile, SceneProfile, VoiceProfile } from "../../types/api";

interface AssetsPageProps {
  characters: CharacterProfile[];
  scenes: SceneProfile[];
  voices: VoiceProfile[];
}

export function AssetsPage({ characters, scenes, voices }: AssetsPageProps) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const normalizedQuery = deferredQuery.trim().toLowerCase();

  const visibleCharacters = characters.filter((character) => {
    if (!normalizedQuery) {
      return true;
    }
    return `${character.name} ${character.appearance} ${character.personality}`.toLowerCase().includes(normalizedQuery);
  });

  const visibleVoices = voices.filter((voice) => {
    if (!normalizedQuery) {
      return true;
    }
    return `${voice.character_name} ${voice.voice_key} ${voice.tone_description}`.toLowerCase().includes(normalizedQuery);
  });

  const visibleScenes = scenes.filter((scene) => {
    if (!normalizedQuery) {
      return true;
    }
    return `${scene.name} ${scene.baseline_prompt} ${scene.continuity_guardrails ?? ""}`
      .toLowerCase()
      .includes(normalizedQuery);
  });

  return (
    <div className="page-stack">
      <SectionCard
        title="角色、场景与音色资产库"
        eyebrow="Asset Library"
        actions={
          <input
            className="search-input"
            placeholder="搜索角色、场景、音色"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        }
      >
        <div className="three-column-grid">
          <div className="asset-column">
            <h3>角色设定卡</h3>
            {visibleCharacters.map((character) => (
              <article className="asset-card" key={character.id}>
                <div className="asset-card-header">
                  <strong>{character.name}</strong>
                  <StatusPill tone={character.review_status === "approved" ? "success" : "warning"}>
                    {character.review_status}
                  </StatusPill>
                </div>
                <p>{character.appearance}</p>
                <p>{character.personality}</p>
                <div className="asset-meta-row">
                  <span>LoRA</span>
                  <code>{character.lora_path ?? "未绑定"}</code>
                </div>
                <div className="asset-meta-row">
                  <span>参考图</span>
                  <span>{character.reference_images.length} 张</span>
                </div>
              </article>
            ))}
          </div>
          <div className="asset-column">
            <h3>场景资产草稿</h3>
            {visibleScenes.map((scene) => (
              <article className="asset-card" key={scene.id}>
                <div className="asset-card-header">
                  <strong>{scene.name}</strong>
                  <StatusPill tone={scene.review_status === "approved" ? "success" : "warning"}>
                    {scene.review_status}
                  </StatusPill>
                </div>
                <p>{scene.baseline_prompt}</p>
                <p>{scene.continuity_guardrails ?? "待补连续性约束"}</p>
              </article>
            ))}
          </div>
          <div className="asset-column">
            <h3>配音一致性库</h3>
            {visibleVoices.map((voice) => (
              <article className="asset-card" key={voice.id}>
                <div className="asset-card-header">
                  <strong>{voice.character_name}</strong>
                  <StatusPill tone="neutral">{voice.provider_key}</StatusPill>
                </div>
                <div className="asset-meta-row">
                  <span>音色 Key</span>
                  <code>{voice.voice_key}</code>
                </div>
                <p>{voice.tone_description}</p>
              </article>
            ))}
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
