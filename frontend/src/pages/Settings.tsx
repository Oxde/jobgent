import { api } from "../lib/api";
import { useLoad } from "../lib/store";
import { ErrorNote, PageHead } from "../components/ui";

export default function Settings() {
  const { data, error } = useLoad(() => api.settings(), []);
  if (error) return <div className="p-7"><ErrorNote message={error} /></div>;
  if (!data) return <div className="p-7 text-text-2">Loading…</div>;
  return (
    <div className="p-7">
      <PageHead title="Settings" />
      <div className="grid gap-4 xl:grid-cols-2">
        <section className="panel">
          <h2 className="mb-2 text-[15px] font-bold">Keys</h2>
          <ul className="divide-y divide-line">
            {data.keys.map((k) => (
              <li key={k.name} className="py-2.5">
                <div className="flex items-center gap-2"><code className="rounded bg-bg-3 px-1.5 py-0.5 text-[12.5px]">{k.name}</code><span className={`tag ${k.present ? "text-ok bg-ok/10" : ""}`}>{k.present ? "set" : "not set"}</span></div>
                <p className="mt-1 text-[12.5px] text-text-2">{k.hint}</p>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[12.5px] text-text-3">Read from the environment or <code>~/.config/secrets/env</code>. Values are never shown here.</p>
        </section>
        <section className="panel">
          <h2 className="mb-2 text-[15px] font-bold">Where things live</h2>
          <ul className="divide-y divide-line text-[13.5px]">
            <li className="py-2.5"><b>Data</b><div className="text-text-2"><code>{data.home_dir}</code></div></li>
            <li className="py-2.5"><b>Company job boards</b><div className="text-text-2">{data.companies} in <code>data/companies.yaml</code></div></li>
            <li className="py-2.5"><b>Models</b><div className="text-text-2">{data.fast_model} for filtering and scoring; {data.smart_model} for writing</div></li>
            <li className="py-2.5"><b>Daily fetch</b><div className="text-text-2"><code>uv run jobgent fetch</code> (cron or launchd), or ask the agent for <code>jobs_fetch</code></div></li>
            <li className="py-2.5"><b>MCP</b><div className="text-text-2"><code>claude mcp add jobgent -- uv --directory &lt;repo&gt; run jobgent mcp</code></div></li>
          </ul>
        </section>
      </div>
    </div>
  );
}
