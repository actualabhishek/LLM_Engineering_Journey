"use client";

import { useState } from "react";
import { categories, projects, type Category } from "@/lib/portfolio";
import { AskButton } from "./ask-button";

type Filter = Category | "All";

export function ProjectsTable() {
  const [filter, setFilter] = useState<Filter>("All");
  const visible = filter === "All" ? projects : projects.filter((project) => project.category === filter);
  const filters: Filter[] = ["All", ...categories];

  return (
    <div>
      <div className="filters" role="group" aria-label="Filter projects by category">
        {filters.map((item) => (
          <button key={item} type="button" className="filter" aria-pressed={filter === item} onClick={() => setFilter(item)}>
            {item}
            <span className="count">{item === "All" ? projects.length : projects.filter((project) => project.category === item).length}</span>
          </button>
        ))}
      </div>

      <ul className="project-list">
        {visible.map((project) => (
          <li key={project.name} className="project-row">
            <div className="project-main">
              <h3>{project.name}</h3>
              <p>{project.summary}</p>
              <ul className="tags" aria-label="Technologies">
                {project.tags.map((tag) => <li key={tag}>{tag}</li>)}
              </ul>
            </div>
            <div className="project-side">
              <span className="project-category">{project.category}</span>
              {project.method && <span className="project-method">Built {project.method === "Independent" ? "independently" : "with Claude Code"}</span>}
              <AskButton question={project.question} className="ask-link">Ask the Twin</AskButton>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
