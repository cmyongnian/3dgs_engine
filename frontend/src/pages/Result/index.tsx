// frontend/src/pages/Result/index.tsx

import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

type AnyObject = Record<string, any>;

interface ResultDetail {
  id?: string;
  task_id?: string;
  taskId?: string;
  status?: string;
  message?: string;
  output_dir?: string;
  outputDir?: string;

  report?: AnyObject | string;
  report_json?: AnyObject | string;
  reportJson?: AnyObject | string;

  report_url?: string;
  reportUrl?: string;
  report_path?: string;
  reportPath?: string;

  metrics?: AnyObject;
  images?: Array<string | AnyObject>;
  artifacts?: Array<string | AnyObject>;
  files?: Array<string | AnyObject>;
  logs?: string | string[];

  [key: string]: any;
}

interface PageState {
  loading: boolean;
  error: string | null;
  result: ResultDetail | null;
  report: AnyObject | null;
}

const API_BASE =
  (import.meta as any).env?.VITE_API_BASE_URL ||
  (import.meta as any).env?.VITE_API_URL ||
  "";

function joinUrl(base: string, path: string) {
  const b = base.endsWith("/") ? base.slice(0, -1) : base;
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${b}${p}`;
}

async function fetchJson<T = any>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }

  return res.json();
}

function isObject(value: unknown): value is AnyObject {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function getByPath(obj: AnyObject | null | undefined, path: string[]) {
  if (!obj) return undefined;

  let cur: any = obj;

  for (const key of path) {
    if (!cur || typeof cur !== "object") return undefined;
    cur = cur[key];
  }

  return cur;
}

function pickFirst(obj: AnyObject | null | undefined, paths: string[][]) {
  for (const path of paths) {
    const value = getByPath(obj, path);

    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }

  return undefined;
}

function normalizeTextList(value: unknown): string[] {
  if (value === undefined || value === null || value === "") return [];

  if (Array.isArray(value)) {
    return value
      .flatMap((item) => normalizeTextList(item))
      .filter((item) => item.trim().length > 0);
  }

  if (typeof value === "string") {
    return value
      .split(/\n+/)
      .map((item) => item.replace(/^[-*•\d.、\s]+/, "").trim())
      .filter(Boolean);
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return [String(value)];
  }

  if (isObject(value)) {
    return Object.entries(value).map(([key, val]) => {
      if (Array.isArray(val)) {
        return `${key}：${val.join("；")}`;
      }

      if (isObject(val)) {
        return `${key}：${JSON.stringify(val, null, 2)}`;
      }

      return `${key}：${String(val)}`;
    });
  }

  return [];
}

function normalizeArray(value: unknown): Array<string | AnyObject> {
  if (!value) return [];

  if (Array.isArray(value)) {
    return value as Array<string | AnyObject>;
  }

  if (typeof value === "string") {
    return [value];
  }

  if (isObject(value)) {
    return Object.values(value).filter(
      (item) => typeof item === "string" || isObject(item)
    ) as Array<string | AnyObject>;
  }

  return [];
}

function normalizeUrl(item: string | AnyObject): string | null {
  if (typeof item === "string") return item;

  return (
    item.url ||
    item.path ||
    item.file ||
    item.file_path ||
    item.filePath ||
    item.src ||
    null
  );
}

function normalizeName(item: string | AnyObject): string {
  if (typeof item === "string") {
    return item.split("/").pop() || item;
  }

  return (
    item.name ||
    item.filename ||
    item.file_name ||
    item.title ||
    normalizeUrl(item)?.split("/").pop() ||
    "文件"
  );
}

function toDisplayUrl(url: string) {
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith("/")) return joinUrl(API_BASE, url);
  return joinUrl(API_BASE, `/${url}`);
}

function isImageUrl(url: string) {
  return /\.(png|jpg|jpeg|webp|gif|bmp|svg)$/i.test(url);
}

function StatusBadge({ status }: { status?: string }) {
  const normalized = (status || "unknown").toLowerCase();

  let label = status || "unknown";
  let className = "status-badge";

  if (["success", "finished", "done", "completed"].includes(normalized)) {
    label = "已完成";
    className += " success";
  } else if (["failed", "error"].includes(normalized)) {
    label = "失败";
    className += " failed";
  } else if (["running", "processing", "training"].includes(normalized)) {
    label = "运行中";
    className += " running";
  } else if (["pending", "queued"].includes(normalized)) {
    label = "等待中";
    className += " pending";
  }

  return <span className={className}>{label}</span>;
}

function InsightCard({
  title,
  items,
  empty,
  type,
}: {
  title: string;
  items: string[];
  empty: string;
  type: "conclusion" | "suggestion";
}) {
  return (
    <section className={`result-card insight-card ${type}`}>
      <div className="result-card-header">
        <h2>{title}</h2>
      </div>

      {items.length > 0 ? (
        <ul className="insight-list">
          {items.map((item, index) => (
            <li key={`${type}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="empty-text">{empty}</p>
      )}
    </section>
  );
}

function MetricsCard({ metrics }: { metrics?: AnyObject }) {
  if (!metrics || Object.keys(metrics).length === 0) return null;

  return (
    <section className="result-card">
      <div className="result-card-header">
        <h2>质量指标</h2>
      </div>

      <div className="metrics-grid">
        {Object.entries(metrics).map(([key, value]) => (
          <div className="metric-item" key={key}>
            <span className="metric-key">{key}</span>
            <span className="metric-value">
              {typeof value === "object"
                ? JSON.stringify(value)
                : String(value)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function ArtifactsCard({
  title,
  items,
}: {
  title: string;
  items?: Array<string | AnyObject>;
}) {
  if (!items || items.length === 0) return null;

  const normalized = items
    .map((item) => {
      const rawUrl = normalizeUrl(item);

      if (!rawUrl) return null;

      return {
        name: normalizeName(item),
        url: toDisplayUrl(rawUrl),
      };
    })
    .filter(Boolean) as Array<{ name: string; url: string }>;

  if (normalized.length === 0) return null;

  const images = normalized.filter((item) => isImageUrl(item.url));
  const files = normalized.filter((item) => !isImageUrl(item.url));

  return (
    <section className="result-card">
      <div className="result-card-header">
        <h2>{title}</h2>
      </div>

      {images.length > 0 && (
        <div className="image-grid">
          {images.map((item, index) => (
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="image-preview"
              key={`${item.url}-${index}`}
            >
              <img src={item.url} alt={item.name} />
              <span>{item.name}</span>
            </a>
          ))}
        </div>
      )}

      {files.length > 0 && (
        <div className="file-list">
          {files.map((item, index) => (
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="file-item"
              key={`${item.url}-${index}`}
            >
              {item.name}
            </a>
          ))}
        </div>
      )}
    </section>
  );
}

function RawReportCard({ report }: { report: AnyObject | null }) {
  if (!report) return null;

  return (
    <section className="result-card">
      <details>
        <summary>查看完整 report.json</summary>
        <pre className="json-preview">{JSON.stringify(report, null, 2)}</pre>
      </details>
    </section>
  );
}

function ResultPage() {
  const params = useParams();

  const taskId =
    params.taskId ||
    params.id ||
    params.runId ||
    params.resultId ||
    "";

  const [state, setState] = useState<PageState>({
    loading: true,
    error: null,
    result: null,
    report: null,
  });

  useEffect(() => {
    let cancelled = false;

    async function loadResultAndReport() {
      if (!taskId) {
        setState({
          loading: false,
          error: "缺少任务 ID，无法加载结果。",
          result: null,
          report: null,
        });
        return;
      }

      setState((prev) => ({
        ...prev,
        loading: true,
        error: null,
      }));

      let result: ResultDetail | null = null;
      let report: AnyObject | null = null;

      const resultUrls = [
        joinUrl(API_BASE, `/api/results/${taskId}`),
        joinUrl(API_BASE, `/results/${taskId}`),
        joinUrl(API_BASE, `/api/tasks/${taskId}/result`),
        joinUrl(API_BASE, `/tasks/${taskId}/result`),
      ];

      let resultError: string | null = null;

      for (const url of resultUrls) {
        try {
          result = await fetchJson<ResultDetail>(url);
          break;
        } catch (err: any) {
          resultError = err?.message || String(err);
        }
      }

      if (result) {
        const embeddedReport =
          result.report ||
          result.report_json ||
          result.reportJson ||
          null;

        if (isObject(embeddedReport)) {
          report = embeddedReport;
        } else if (typeof embeddedReport === "string") {
          try {
            report = JSON.parse(embeddedReport);
          } catch {
            // 可能是 URL，下面继续尝试 fetch
          }
        }
      }

      if (!report) {
        const reportUrlFromResult =
          result?.report_url ||
          result?.reportUrl ||
          result?.report_path ||
          result?.reportPath ||
          "";

        const reportUrls = [
          reportUrlFromResult,
          joinUrl(API_BASE, `/api/results/${taskId}/report`),
          joinUrl(API_BASE, `/api/results/${taskId}/report.json`),
          joinUrl(API_BASE, `/results/${taskId}/report`),
          joinUrl(API_BASE, `/results/${taskId}/report.json`),
          joinUrl(API_BASE, `/outputs/${taskId}/report.json`),
          joinUrl(API_BASE, `/static/results/${taskId}/report.json`),
        ].filter(Boolean);

        for (const url of reportUrls) {
          try {
            report = await fetchJson<AnyObject>(url);
            break;
          } catch {
            // 继续尝试下一个路径
          }
        }
      }

      if (cancelled) return;

      if (!result && !report) {
        setState({
          loading: false,
          error:
            resultError ||
            "结果加载失败，请确认后端是否提供结果查询接口和 report.json。",
          result: null,
          report: null,
        });
        return;
      }

      setState({
        loading: false,
        error: null,
        result,
        report,
      });
    }

    loadResultAndReport();

    return () => {
      cancelled = true;
    };
  }, [taskId]);

  const report = state.report;

  const autoConclusions = useMemo(() => {
    const value = pickFirst(report, [
      ["自动结论"],
      ["auto_conclusion"],
      ["automatic_conclusion"],
      ["autoConclusion"],
      ["conclusion"],

      ["summary", "自动结论"],
      ["summary", "auto_conclusion"],
      ["summary", "automatic_conclusion"],
      ["summary", "conclusion"],

      ["quality", "自动结论"],
      ["quality", "auto_conclusion"],
      ["quality", "conclusion"],

      ["analysis", "自动结论"],
      ["analysis", "auto_conclusion"],
      ["analysis", "conclusion"],

      ["colmap_quality", "自动结论"],
      ["colmap_quality", "auto_conclusion"],
      ["colmap_quality", "conclusion"],

      ["quality_analysis", "自动结论"],
      ["quality_analysis", "auto_conclusion"],
      ["quality_analysis", "conclusion"],
    ]);

    return normalizeTextList(value);
  }, [report]);

  const optimizationSuggestions = useMemo(() => {
    const value = pickFirst(report, [
      ["优化建议"],
      ["optimization_suggestions"],
      ["optimizationSuggestions"],
      ["suggestions"],
      ["recommendations"],
      ["next_steps"],
      ["nextSteps"],

      ["summary", "优化建议"],
      ["summary", "optimization_suggestions"],
      ["summary", "suggestions"],
      ["summary", "recommendations"],

      ["quality", "优化建议"],
      ["quality", "optimization_suggestions"],
      ["quality", "suggestions"],
      ["quality", "recommendations"],

      ["analysis", "优化建议"],
      ["analysis", "optimization_suggestions"],
      ["analysis", "suggestions"],
      ["analysis", "recommendations"],

      ["colmap_quality", "优化建议"],
      ["colmap_quality", "optimization_suggestions"],
      ["colmap_quality", "suggestions"],
      ["colmap_quality", "recommendations"],

      ["quality_analysis", "优化建议"],
      ["quality_analysis", "optimization_suggestions"],
      ["quality_analysis", "suggestions"],
      ["quality_analysis", "recommendations"],
    ]);

    return normalizeTextList(value);
  }, [report]);

  const mergedMetrics = useMemo(() => {
    const value =
      state.result?.metrics ||
      report?.metrics ||
      report?.quality_metrics ||
      report?.qualityMetrics ||
      report?.colmap_metrics ||
      report?.colmapMetrics ||
      report?.colmap_quality?.metrics ||
      report?.quality_analysis?.metrics;

    return isObject(value) ? value : undefined;
  }, [state.result, report]);

  const artifacts = useMemo(() => {
    return normalizeArray(
      state.result?.artifacts ||
        state.result?.files ||
        report?.artifacts ||
        report?.files ||
        report?.outputs ||
        report?.output_files
    );
  }, [state.result, report]);

  const images = useMemo(() => {
    return normalizeArray(
      state.result?.images ||
        report?.images ||
        report?.previews ||
        report?.preview_images ||
        report?.visualizations
    );
  }, [state.result, report]);

  if (state.loading) {
    return (
      <div className="result-page">
        <div className="result-header">
          <div>
            <h1>结果详情</h1>
            <p>正在加载任务结果和 report.json...</p>
          </div>
        </div>
      </div>
    );
  }

  if (state.error) {
    return (
      <div className="result-page">
        <div className="result-header">
          <div>
            <h1>结果详情</h1>
            <p className="error-text">{state.error}</p>
          </div>

          <Link to="/" className="back-link">
            返回首页
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="result-page">
      <div className="result-header">
        <div>
          <h1>结果详情</h1>
          <p>
            任务 ID：
            <span className="mono-text">
              {state.result?.task_id ||
                state.result?.taskId ||
                state.result?.id ||
                taskId}
            </span>
          </p>
        </div>

        <div className="result-header-actions">
          <StatusBadge status={state.result?.status} />

          <Link to="/" className="back-link">
            返回首页
          </Link>
        </div>
      </div>

      <div className="result-grid">
        <InsightCard
          title="自动结论"
          type="conclusion"
          items={autoConclusions}
          empty="report.json 中暂未找到自动结论字段。"
        />

        <InsightCard
          title="优化建议"
          type="suggestion"
          items={optimizationSuggestions}
          empty="report.json 中暂未找到优化建议字段。"
        />
      </div>

      <MetricsCard metrics={mergedMetrics} />

      <ArtifactsCard title="结果预览" items={images} />

      <ArtifactsCard title="输出文件" items={artifacts} />

      {state.result?.message && (
        <section className="result-card">
          <div className="result-card-header">
            <h2>运行信息</h2>
          </div>
          <p>{state.result.message}</p>
        </section>
      )}

      {state.result?.logs && (
        <section className="result-card">
          <details>
            <summary>查看运行日志</summary>
            <pre className="log-preview">
              {Array.isArray(state.result.logs)
                ? state.result.logs.join("\n")
                : state.result.logs}
            </pre>
          </details>
        </section>
      )}

      <RawReportCard report={report} />
    </div>
  );
}

export { ResultPage };
export default ResultPage;