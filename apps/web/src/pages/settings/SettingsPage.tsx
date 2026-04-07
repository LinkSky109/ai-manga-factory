import { useState } from "react";

import { SectionCard } from "../../components/stitch/SectionCard";
import { StatusPill } from "../../components/stitch/StatusPill";
import { api } from "../../lib/api";
import type { AuditLogRecord, AuthSession, ProviderConfigRecord, SettingsOverview } from "../../types/api";

interface SettingsPageProps {
  authSession: AuthSession;
  settingsOverview: SettingsOverview;
  auditLogs: AuditLogRecord[];
  sampleMode: boolean;
  onReload: () => void;
}

export function SettingsPage({
  authSession,
  settingsOverview,
  auditLogs,
  sampleMode,
  onReload,
}: SettingsPageProps) {
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const toggleProvider = async (provider: ProviderConfigRecord) => {
    setSavingKey(provider.provider_key);
    setMessage(null);

    if (sampleMode) {
      window.setTimeout(() => {
        setSavingKey(null);
        setMessage(`sample: ${provider.provider_key} 已模拟切换。`);
      }, 150);
      return;
    }

    try {
      await api.updateProviderConfig(provider.provider_key, {
        is_enabled: !provider.is_enabled,
      });
      setMessage(`${provider.provider_key} 已更新。`);
      onReload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "更新失败");
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <div className="page-stack" data-testid="page-settings">
      <div className="two-column-grid">
        <SectionCard title="认证与权限" eyebrow="Security">
          <div className="stack-list">
            <div className="list-row">
              <span>认证状态</span>
              <StatusPill tone={settingsOverview.auth.enabled ? "success" : "warning"}>
                {settingsOverview.auth.enabled ? "enabled" : "disabled"}
              </StatusPill>
            </div>
            <div data-testid="auth-state" hidden>
              {settingsOverview.auth.enabled ? "enabled" : "disabled"}
            </div>
            <div className="list-row">
              <span>当前身份</span>
              <StatusPill tone={authSession.role === "admin" ? "success" : "neutral"}>
                {authSession.role ?? "anonymous"}
              </StatusPill>
            </div>
            <p className="muted-copy">
              {authSession.display_name ?? "未注入访问令牌"} {authSession.email ? `· ${authSession.email}` : ""}
            </p>
            {settingsOverview.auth.bootstrap_accounts.map((account) => (
              <div className="list-row" key={`${account.role}-${account.email}`}>
                <span>{account.display_name}</span>
                <StatusPill tone="neutral">{account.role}</StatusPill>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="运行配置" eyebrow="Runtime">
          <div className="stack-list">
            <div className="list-row">
              <span>环境</span>
              <StatusPill tone="neutral">{settingsOverview.runtime.environment}</StatusPill>
            </div>
            <div className="list-row">
              <span>默认路由</span>
              <StatusPill tone="neutral">{settingsOverview.runtime.default_routing_mode}</StatusPill>
            </div>
            <div className="list-row">
              <span>对象存储</span>
              <StatusPill tone="neutral">{settingsOverview.runtime.object_storage_mode}</StatusPill>
            </div>
            <p className="muted-copy">{settingsOverview.runtime.archive_targets.join(" / ")}</p>
          </div>
        </SectionCard>
      </div>

      <SectionCard title="Provider 配置中心" eyebrow="Config Center">
        <div className="stack-list">
          {settingsOverview.providers.map((provider) => (
            <article className="review-card" key={provider.provider_key}>
              <div className="asset-card-header">
                <strong>{provider.provider_key}</strong>
                <StatusPill tone={provider.is_enabled ? "success" : "danger"}>
                  {provider.is_enabled ? "enabled" : "disabled"}
                </StatusPill>
              </div>
              <div className="list-row">
                <span>{provider.provider_type}</span>
                <StatusPill tone="neutral">{`priority ${String(provider.priority)}`}</StatusPill>
              </div>
              <div className="list-row">
                <span>routing</span>
                <StatusPill tone="neutral">{provider.routing_mode}</StatusPill>
              </div>
              <p className="muted-copy">
                threshold {provider.budget_threshold} · {JSON.stringify(provider.config)}
              </p>
              <button
                className="refresh-button"
                type="button"
                disabled={savingKey === provider.provider_key}
                onClick={() => void toggleProvider(provider)}
              >
                {savingKey === provider.provider_key
                  ? "保存中"
                  : provider.is_enabled
                    ? "禁用 Provider"
                    : "启用 Provider"}
              </button>
            </article>
          ))}
          {message ? <div className="notice-banner warning">{message}</div> : null}
        </div>
      </SectionCard>

      <div className="two-column-grid">
        <SectionCard title="归档后端" eyebrow="Storage Targets">
          <div className="stack-list">
            {settingsOverview.storage_targets.map((target) => (
              <article className="review-card" key={target.archive_type}>
                <div className="asset-card-header">
                  <strong>{target.archive_type}</strong>
                  <StatusPill tone={target.is_ready ? "success" : "danger"}>
                    {target.is_ready ? "ready" : "blocked"}
                  </StatusPill>
                </div>
                <p>{target.mode}</p>
                <p className="muted-copy">{target.readiness_reason}</p>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="审计日志" eyebrow="Audit Trail">
          <div className="stack-list">
            {auditLogs.slice(0, 8).map((item) => (
              <article className="review-card" key={item.id}>
                <div className="asset-card-header">
                  <strong>{item.action}</strong>
                  <StatusPill tone={item.outcome === "success" ? "success" : "warning"}>{item.outcome}</StatusPill>
                </div>
                <p>{item.request_path}</p>
                <p className="muted-copy">
                  {item.actor_email ?? "anonymous"} · {item.actor_role ?? "n/a"} · {item.response_status}
                </p>
              </article>
            ))}
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
