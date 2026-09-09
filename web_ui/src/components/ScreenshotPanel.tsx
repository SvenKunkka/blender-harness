import type { RunDetail } from "../types";
import { StatusPill } from "./pills";

export interface ScreenshotPanelProps {
  /** Currently displayed run (active or loaded from history). */
  run: RunDetail | null;
  /** URL of the most recent captured screenshot (from history). */
  fallbackUrl: string | null;
}

const VERDICT_CLASS: Record<string, string> = {
  PASS: "verdict-pass",
  REFINE: "verdict-refine",
  SKIPPED: "verdict-skipped",
};

export function ScreenshotPanel({ run, fallbackUrl }: ScreenshotPanelProps) {
  const mainUrl = run?.screenshot_url ?? fallbackUrl;
  const vision = run?.vision ?? [];

  return (
    <section className="panel shot-panel" aria-label="Viewport screenshot">
      <div className="panel-head">
        <span className="panel-title">Viewport preview</span>
        <span className="head-spacer" />
        {run ? (
          <>
            <StatusPill tone={run.status} label={run.status} />
            {run.vision.length > 0 ? (
              <span className="muted small mono">
                vision {run.vision.length}
              </span>
            ) : null}
          </>
        ) : (
          <span className="muted small">no run loaded</span>
        )}
      </div>

      <div className="shot-body">
        {mainUrl ? (
          <div className="shot-stage">
            <img
              className="shot-img"
              src={mainUrl}
              alt={run ? `Viewport screenshot for run ${run.run_id}` : "Last viewport screenshot"}
              draggable={false}
            />
            {run && run.prompt ? (
              <div className="shot-caption mono">
                {run.prompt}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="shot-placeholder">
            <div className="shot-glyph" aria-hidden="true">
              ◫
            </div>
            <div>No screenshot yet</div>
            <div className="muted small">
              Start a run to see Blender's viewport here; agent screenshots and
              vision review frames appear as they are captured.
            </div>
          </div>
        )}

        {vision.length > 0 ? (
          <div className="vision-block">
            <div className="vision-head">
              <span className="panel-title small">Vision reviews</span>
            </div>
            {vision.map((review) => (
              <div key={review.round} className="vision-review">
                <div className="vision-top">
                  <span className="vision-round mono">round {review.round}</span>
                  <span
                    className={`verdict ${VERDICT_CLASS[review.verdict] ?? "verdict-skipped"}`}
                  >
                    {review.verdict}
                  </span>
                </div>
                <div className="vision-thumbs">
                  {review.image_urls.map((url, i) => (
                    <img
                      key={`${url}-${i}`}
                      className="vision-thumb"
                      src={url}
                      alt={`Vision review round ${review.round} frame ${i + 1}`}
                      loading="lazy"
                    />
                  ))}
                </div>
                {review.issues.length > 0 ? (
                  <ul className="vision-issues">
                    {review.issues.map((issue, i) => (
                      <li key={`${issue}-${i}`}>{issue}</li>
                    ))}
                  </ul>
                ) : null}
                {review.comment ? (
                  <p className="vision-comment muted">{review.comment}</p>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
