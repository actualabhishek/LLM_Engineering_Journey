const LINKS = [
  "Dashboard",
  "Boards",
  "Change Requests",
  "Incidents",
  "Maintenance Windows",
  "Reports",
  "Team",
  "Settings",
];

export function Sidebar() {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-nav text-ink">
      <div className="px-5 py-5">
        <p className="text-sm font-semibold tracking-wide">NetOps Flow</p>
      </div>
      <nav className="flex-1 px-3">
        <ul className="flex flex-col gap-0.5">
          {LINKS.map((link) => {
            const active = link === "Boards";
            return (
              <li key={link}>
                <a
                  href="#"
                  aria-current={active ? "page" : undefined}
                  onClick={(e) => {
                    if (!active) e.preventDefault();
                  }}
                  className={`block rounded-lg px-3 py-2 text-sm transition-colors ${
                    active
                      ? "bg-accent-solid font-medium text-white"
                      : "text-muted hover:bg-white/5 hover:text-ink"
                  }`}
                >
                  {link}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
