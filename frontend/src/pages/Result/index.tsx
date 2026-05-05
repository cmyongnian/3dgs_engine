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

function formatDateTime(value: unknown) {
  if (!value) return "-";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatValue(value: unknown, digits = 4) {
  if (value === undefined || value === null || value === "") return "-";

  if (typeof value === "boolean") {
    return value ? "开启" : "关闭";
  }

  const numberValue = typeof value === "number" ? value : Number(value);
  if (Number.isFinite(numberValue) && String(value).trim() !== "") {
    if (Math.abs(numberValue) >= 1000) return String(Math.round(numberValue));
    return numberValue
      .toFixed(digits)
      .replace(/\.0+$/, "")
      .replace(/(\.\d*?)0+$/, "$1");
  }

  if (Array.isArray(value)) return value.join("，");
  if (isObject(value)) return JSON.stringify(value);
  return String(value);
}

function pathValue(value: unknown) {
  const text = formatValue(value);
  if (text === "-") return text;
  return text.replace(/\\/g, "/");
}

function metricValue(source: AnyObject | null | undefined, key: string) {
  return pickFirst(source, [
    ["metrics_summary", key],
    ["metrics", key],
    ["experiment_info", "metrics_summary", key],
    ["result", "metrics_summary", key],
    ["result", "experiment_info", "metrics_summary", key],
  ]);
}

function getExperimentInfo(result: ResultDetail | null): AnyObject {
  const info = pickFirst(result, [
    ["experiment_info"],
    ["experimentInfo"],
    ["result", "experiment_info"],
    ["result", "experimentInfo"],
  ]);
  return isObject(info) ? info : {};
}

function getConfigSnapshot(result: ResultDetail | null): AnyObject {
  const snapshot = pickFirst(result, [
    ["config_snapshot"],
    ["configSnapshot"],
    ["result", "config_snapshot"],
    ["result", "configSnapshot"],
  ]);
  return isObject(snapshot) ? snapshot : {};
}

function getAugmentationReport(result: ResultDetail | null, report: AnyObject | null): AnyObject {
  const value = pickFirst(result, [
    ["augmentation_report"],
    ["augmentationReport"],
    ["result", "augmentation_report"],
    ["result", "augmentationReport"],
  ]) || pickFirst(report, [["augmentation_report"], ["augmentationReport"]]);

  return isObject(value) ? value : {};
}

function getActiveTrainProfile(config: AnyObject): AnyObject {
  const train = isObject(config.train) ? config.train : {};
  const activeProfile = train.active_profile || "";
  const profiles = isObject(train.profiles) ? train.profiles : {};
  const profile = activeProfile && isObject(profiles[activeProfile]) ? profiles[activeProfile] : {};
  const activeProfileData = isObject(train.active_profile_data) ? train.active_profile_data : {};

  return {
    active_profile: activeProfile,
    ...(isObject(profile) ? profile : {}),
    ...(isObject(activeProfileData) ? activeProfileData : {}),
  };
}

function InfoItem({ label, value, mono = false }: { label: string; value: unknown; mono?: boolean }) {
  return (
    <div className="experiment-info-item">
      <span>{label}</span>
      <strong className={mono ? "mono-value" : undefined} title={String(formatValue(value))}>
        {mono ? pathValue(value) : formatValue(value)}
      </strong>
    </div>
  );
}

function FlowFlag({ label, value }: { label: string; value: unknown }) {
  const enabled = value === true || value === "true" || value === 1 || value === "1";
  const disabled = value === false || value === "false" || value === 0 || value === "0";
  return (
    <span className={`flow-flag ${enabled ? "flow-flag-on" : disabled ? "flow-flag-off" : ""}`}>
      {label}：{enabled ? "开" : disabled ? "关" : formatValue(value)}
    </span>
  );
}

function ExperimentInfoCard({
  result,
  taskId,
}: {
  result: ResultDetail | null;
  taskId: string;
}) {
  const info = getExperimentInfo(result);
  const config = getConfigSnapshot(result);
  const trainProfile = isObject(info.train_profile) ? info.train_profile : {};
  const pipeline = isObject(config.pipeline) ? config.pipeline : {};
  const augmentation = isObject(config.augmentation) ? config.augmentation : {};

  const registrationRate = metricValue(result, "colmap_registration_rate");

  return (
    <section className="result-card experiment-info-card">
      <div className="result-card-header">
        <div>
          <h2>实验信息</h2>
          <p className="section-tip">
            用于论文实验记录和多任务对比，重点展示任务隔离目录、数据增强状态、训练配置和关键指标。
          </p>
        </div>
      </div>

      <div className="experiment-info-grid">
        <InfoItem label="任务 ID" value={info.task_id || result?.task_id || result?.id || taskId} />
        <InfoItem label="场景名称" value={info.scene_name || result?.scene_name} />
        <InfoItem label="输入模式" value={info.input_mode === "video" ? "视频抽帧" : info.input_mode === "images" ? "图片目录" : info.input_mode} />
        <InfoItem label="任务状态" value={info.status || result?.status} />
        <InfoItem label="创建时间" value={formatDateTime(info.created_at || result?.created_at)} />
        <InfoItem label="完成时间" value={formatDateTime(info.finished_at || result?.finished_at)} />
        <InfoItem label="数据增强" value={info.augmentation_enabled} />
        <InfoItem label="增强预设" value={info.augmentation_preset || augmentation.preset} />
        <InfoItem label="训练模板" value={trainProfile.active_profile} />
        <InfoItem label="训练轮数" value={trainProfile.iterations} />
        <InfoItem label="分辨率倍率" value={trainProfile.resolution} />
        <InfoItem label="数据设备" value={trainProfile.data_device} />
        <InfoItem label="COLMAP GPU" value={info.colmap_use_gpu} />
        <InfoItem label="视频 FPS" value={info.video_target_fps} />
        <InfoItem label="PSNR" value={metricValue(result, "psnr")} />
        <InfoItem label="SSIM" value={metricValue(result, "ssim")} />
        <InfoItem label="LPIPS" value={metricValue(result, "lpips")} />
        <InfoItem label="COLMAP 注册率" value={registrationRate === undefined || registrationRate === null || registrationRate === "" ? "-" : `${formatValue(registrationRate, 2)}%`} />
      </div>

      <div className="experiment-path-grid">
        <InfoItem label="原始图片目录" value={info.raw_image_dir} mono />
        <InfoItem label="处理目录" value={info.processed_dir} mono />
        <InfoItem label="训练输入目录" value={info.source_dir} mono />
        <InfoItem label="模型输出目录" value={info.output_dir} mono />
        <InfoItem label="增强输出目录" value={info.augmentation_output_dir} mono />
        <InfoItem label="运行配置目录" value={info.runtime_dir} mono />
      </div>

      <div className="flow-flag-wrap">
        <FlowFlag label="预检查" value={pipeline.run_preflight} />
        <FlowFlag label="视频抽帧" value={pipeline.run_video_extract} />
        <FlowFlag label="数据增强" value={pipeline.run_augmentation} />
        <FlowFlag label="COLMAP" value={pipeline.run_colmap} />
        <FlowFlag label="转换" value={pipeline.run_convert} />
        <FlowFlag label="训练" value={pipeline.run_train} />
        <FlowFlag label="渲染" value={pipeline.run_render} />
        <FlowFlag label="评测" value={pipeline.run_metrics} />
      </div>
    </section>
  );
}

function KeyValueGrid({
  rows,
  mono = false,
}: {
  rows: Array<[string, unknown]>;
  mono?: boolean;
}) {
  const filtered = rows.filter(([, value]) => value !== undefined && value !== null && value !== "");

  if (filtered.length === 0) {
    return <p className="empty-text">暂无参数。</p>;
  }

  return (
    <div className="param-kv-grid">
      {filtered.map(([label, value]) => (
        <div className="param-kv-item" key={label}>
          <span>{label}</span>
          <strong className={mono ? "mono-value" : undefined} title={pathValue(value)}>
            {mono ? pathValue(value) : formatValue(value)}
          </strong>
        </div>
      ))}
    </div>
  );
}

function ParameterSnapshotCard({ result }: { result: ResultDetail | null }) {
  const config = getConfigSnapshot(result);

  if (!config || Object.keys(config).length === 0) return null;

  const pipeline = isObject(config.pipeline) ? config.pipeline : {};
  const augmentation = isObject(config.augmentation) ? config.augmentation : {};
  const trainProfile = getActiveTrainProfile(config);
  const trainExtra = isObject(trainProfile.extra_args) ? trainProfile.extra_args : {};
  const colmap = isObject(config.colmap) ? config.colmap : {};
  const video = isObject(config.video) ? config.video : {};

  return (
    <section className="result-card parameter-snapshot-card">
      <div className="result-card-header">
        <div>
          <h2>参数快照</h2>
          <p className="section-tip">
            展示本任务运行时生成的配置文件内容。这里读取的是该任务自己的 runtime 目录，不受当前系统设置变化影响。
          </p>
        </div>
      </div>

      <div className="param-section-grid">
        <div className="param-section">
          <h3>训练参数</h3>
          <KeyValueGrid
            rows={[
              ["训练模板", trainProfile.active_profile],
              ["训练轮数", trainProfile.iterations],
              ["保存轮数", trainProfile.save_iterations],
              ["测试轮数", trainProfile.test_iterations],
              ["检查点轮数", trainProfile.checkpoint_iterations],
              ["eval", trainProfile.eval],
              ["data_device", trainExtra.data_device],
              ["resolution", trainExtra.resolution],
              ["densify_grad_threshold", trainExtra.densify_grad_threshold],
              ["densification_interval", trainExtra.densification_interval],
              ["densify_until_iter", trainExtra.densify_until_iter],
            ]}
          />
        </div>

        <div className="param-section">
          <h3>数据增强参数</h3>
          <KeyValueGrid
            rows={[
              ["enabled", augmentation.enabled],
              ["preset", augmentation.preset],
              ["gray_world", augmentation.gray_world],
              ["clahe", augmentation.clahe],
              ["clahe_clip_limit", augmentation.clahe_clip_limit],
              ["clahe_tile_grid_size", augmentation.clahe_tile_grid_size],
              ["auto_gamma", augmentation.auto_gamma],
              ["gamma_target_mean", augmentation.gamma_target_mean],
              ["denoise", augmentation.denoise],
              ["denoise_h", augmentation.denoise_h],
              ["sharpen", augmentation.sharpen],
              ["sharpen_amount", augmentation.sharpen_amount],
              ["jpeg_quality", augmentation.jpeg_quality],
              ["max_long_edge", augmentation.max_long_edge],
            ]}
          />
        </div>

        <div className="param-section">
          <h3>COLMAP / 视频参数</h3>
          <KeyValueGrid
            rows={[
              ["COLMAP GPU", colmap.use_gpu],
              ["COLMAP 图片目录", colmap.image_path],
              ["COLMAP 工作目录", colmap.workspace_path],
              ["COLMAP 程序", colmap.colmap_executable],
              ["视频路径", video.video_path],
              ["抽帧 FPS", video.target_fps],
              ["FFmpeg", video.ffmpeg_executable],
            ]}
            mono
          />
        </div>

        <div className="param-section">
          <h3>流程开关</h3>
          <div className="flow-flag-wrap compact">
            <FlowFlag label="预检查" value={pipeline.run_preflight} />
            <FlowFlag label="视频抽帧" value={pipeline.run_video_extract} />
            <FlowFlag label="数据增强" value={pipeline.run_augmentation} />
            <FlowFlag label="COLMAP" value={pipeline.run_colmap} />
            <FlowFlag label="转换" value={pipeline.run_convert} />
            <FlowFlag label="训练" value={pipeline.run_train} />
            <FlowFlag label="渲染" value={pipeline.run_render} />
            <FlowFlag label="评测" value={pipeline.run_metrics} />
          </div>
        </div>
      </div>

      <details className="snapshot-details">
        <summary>查看完整运行时配置快照</summary>
        <pre className="json-preview">{JSON.stringify(config, null, 2)}</pre>
      </details>
    </section>
  );
}

function AugmentationReportCard({
  result,
  report,
}: {
  result: ResultDetail | null;
  report: AnyObject | null;
}) {
  const augmentationReport = getAugmentationReport(result, report);
  const config = getConfigSnapshot(result);
  const augmentationCfg = isObject(config.augmentation) ? config.augmentation : {};
  const shouldShow = Object.keys(augmentationReport).length > 0 || augmentationCfg.enabled === true;

  if (!shouldShow) return null;

  const counts = isObject(augmentationReport.counts) ? augmentationReport.counts : {};
  const method = isObject(augmentationReport.method) ? augmentationReport.method : {};
  const operations = isObject(method.operations) ? method.operations : {};
  const parameters = isObject(method.parameters) ? method.parameters : augmentationCfg;
  const items = Array.isArray(augmentationReport.items) ? augmentationReport.items : [];
  const failedItems = items.filter((item: any) => item?.status === "failed" || item?.status === "skipped").slice(0, 8);

  return (
    <section className="result-card augmentation-report-card">
      <div className="result-card-header">
        <div>
          <h2>数据增强报告</h2>
          <p className="section-tip">
            用于说明增强模块是否执行成功，以及是否保持 3DGS / COLMAP 所需的几何一致性。
          </p>
        </div>
      </div>

      {Object.keys(augmentationReport).length === 0 ? (
        <p className="empty-text">
          当前任务开启了数据增强，但暂未找到 augmentation_report.json。请确认数据增强阶段是否已经执行完成。
        </p>
      ) : (
        <>
          <div className="augmentation-summary-grid">
            <InfoItem label="增强状态" value={augmentationReport.enabled} />
            <InfoItem label="增强预设" value={augmentationReport.preset || parameters.preset} />
            <InfoItem label="输入图片" value={counts.input_images ?? augmentationReport.total} />
            <InfoItem label="成功增强" value={counts.success_images ?? augmentationReport.success} />
            <InfoItem label="失败图片" value={counts.failed_images ?? augmentationReport.failed} />
            <InfoItem label="复制原图" value={counts.copied_original_images ?? augmentationReport.skipped} />
            <InfoItem label="增强库" value={method.library} />
            <InfoItem label="几何变换" value={method.geometric_transforms ? "使用" : "未使用"} />
          </div>

          <div className="experiment-path-grid">
            <InfoItem label="增强输入目录" value={augmentationReport.input_images} mono />
            <InfoItem label="增强输出目录" value={augmentationReport.output_images} mono />
          </div>

          <div className="operation-tag-wrap">
            {Object.entries(operations).map(([key, value]) => (
              <span className={`operation-tag ${value ? "on" : "off"}`} key={key}>
                {key}：{value ? "开" : "关"}
              </span>
            ))}
          </div>

          <div className="param-section soft">
            <h3>增强参数</h3>
            <KeyValueGrid
              rows={[
                ["jpeg_quality", parameters.jpeg_quality],
                ["clahe_clip_limit", parameters.clahe_clip_limit],
                ["clahe_tile_grid_size", parameters.clahe_tile_grid_size],
                ["gamma_target_mean", parameters.gamma_target_mean],
                ["denoise_h", parameters.denoise_h],
                ["sharpen_amount", parameters.sharpen_amount],
                ["max_long_edge", parameters.max_long_edge],
                ["keep_original_if_failed", parameters.keep_original_if_failed],
              ]}
            />
          </div>

          {method.notes && <p className="safe-note">{method.notes}</p>}

          {failedItems.length > 0 && (
            <details className="snapshot-details">
              <summary>查看失败或复制原图记录</summary>
              <pre className="json-preview">{JSON.stringify(failedItems, null, 2)}</pre>
            </details>
          )}
        </>
      )}
    </section>
  );
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
          result.report_summary ||
          result.reportSummary ||
          result.result?.report_summary ||
          result.result?.reportSummary ||
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
          result?.result_files?.report_json ||
          result?.resultFiles?.report_json ||
          result?.result?.result_files?.report_json ||
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
      ["overall_conclusion"],
      ["overallConclusion"],
      ["conclusion"],

      ["summary", "自动结论"],
      ["summary", "auto_conclusion"],
      ["summary", "automatic_conclusion"],
      ["summary", "overall_conclusion"],
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
      state.result?.metrics_summary ||
      state.result?.metricsSummary ||
      state.result?.metrics ||
      state.result?.result?.metrics_summary ||
      state.result?.result?.metricsSummary ||
      report?.metrics_summary ||
      report?.metricsSummary ||
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
        state.result?.result_files ||
        state.result?.resultFiles ||
        state.result?.result?.artifacts ||
        state.result?.result?.files ||
        state.result?.result?.result_files ||
        report?.artifacts ||
        report?.files ||
        report?.outputs ||
        report?.output_files ||
        report?.result_files
    );
  }, [state.result, report]);

  const images = useMemo(() => {
    return normalizeArray(
      state.result?.images ||
        state.result?.result?.images ||
        state.result?.result?.preview_images ||
        state.result?.result?.previewImages ||
        report?.images ||
        report?.previews ||
        report?.preview_images ||
        report?.previewImages ||
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

      <ExperimentInfoCard result={state.result} taskId={taskId || ""} />

      <ParameterSnapshotCard result={state.result} />

      <AugmentationReportCard result={state.result} report={report} />

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