import { AppShell } from "@/components/app-shell";
import { AskButton } from "@/components/ask-button";
import { ProjectsTable } from "@/components/projects-table";
import { capabilities, experience, facts, profile } from "@/lib/portfolio";

export default function Home() {
  return (
    <AppShell email={profile.email}>
      <section className="intro" aria-labelledby="intro-title">
        <p className="role">{profile.role}</p>
        <h1 id="intro-title">Network engineer building GenAI systems for operations.</h1>
        <p className="lede">{profile.summary}</p>
        <div className="intro-actions">
          <AskButton question="What are you working on right now, and what kind of role are you looking for?" className="primary">Ask what I’m working on</AskButton>
          <a className="plain" href={profile.github} target="_blank" rel="noreferrer">Read the build log on GitHub</a>
        </div>
        <dl className="facts">
          {facts.map((fact) => (
            <div key={fact.label}>
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section id="work" className="block" aria-labelledby="work-title">
        <div className="block-head">
          <h2 id="work-title">Projects</h2>
          <p>Each one points at a real operations problem. Pick a row to question the Twin about it.</p>
        </div>
        <ProjectsTable />
      </section>

      <section id="capabilities" className="block" aria-labelledby="skills-title">
        <div className="block-head">
          <h2 id="skills-title">Skills</h2>
        </div>
        <dl className="spec">
          {capabilities.map((capability) => (
            <div key={capability.label}>
              <dt>{capability.label}</dt>
              <dd>{capability.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section id="experience" className="block" aria-labelledby="experience-title">
        <div className="block-head">
          <h2 id="experience-title">Experience</h2>
        </div>
        <ol className="history">
          {experience.map((item) => (
            <li key={`${item.period}-${item.company}`}>
              <time>{item.period}</time>
              <div>
                <h3>{item.role}</h3>
                <p className="company">{item.company}</p>
                <p>{item.note}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <footer className="footer">
        <p>{profile.name}, based in {profile.location}.</p>
        <p className="footer-links">
          <a href={profile.linkedin} target="_blank" rel="noreferrer">LinkedIn</a>
          <a href={profile.github} target="_blank" rel="noreferrer">GitHub</a>
          <a href={`mailto:${profile.email}`}>Email</a>
        </p>
      </footer>
    </AppShell>
  );
}
