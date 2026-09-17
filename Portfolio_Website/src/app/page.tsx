import { DigitalTwin } from "@/components/digital-twin";
import { capabilities, experience, profile, projects } from "@/lib/portfolio";

function Arrow() { return <span aria-hidden="true">↗</span>; }

export default function Home() {
  return (
    <main>
      <div className="shell">
        <header className="topbar">
          <a href="#top" className="wordmark"><span>AS</span> Abhishek Suman</a>
          <nav aria-label="Main navigation"><a href="#work">Work</a><a href="#experience">Experience</a><a href="#twin">Digital Twin</a></nav>
          <a href={`mailto:${profile.email}`} className="contact-link">Contact <Arrow /></a>
        </header>

        <section id="top" className="hero">
          <div className="hero-copy">
            <p className="eyebrow">Network systems × generative AI</p>
            <h1>Built on infrastructure.<br /><em>Focused on intelligence.</em></h1>
            <p className="intro">{profile.summary}</p>
            <div className="actions"><a className="button" href="#twin">Talk to my Digital Twin <Arrow /></a><a className="text-link" href={profile.github} target="_blank" rel="noreferrer">View build log <Arrow /></a></div>
          </div>
          <aside className="signal-board" aria-label="Professional summary">
            <div className="board-head"><span>ENGINEERING SIGNAL</span><span className="status"><i /> Available</span></div>
            <div className="metric"><strong>16+</strong><span>years in enterprise IT</span></div>
            <div className="metric-grid"><div><b>2021—</b><small>TCS</small></div><div><b>RAG</b><small>retrieval systems</small></div><div><b>LLM</b><small>agent workflows</small></div><div><b>NET</b><small>enterprise ops</small></div></div>
            <p className="board-foot">Based in {profile.location}<br />Transitioning into GenAI/LLM engineering.</p>
          </aside>
        </section>

        <section className="capabilities" aria-label="Capabilities">
          {capabilities.map((capability, index) => <div key={capability.label}><span>0{index + 1}</span><h2>{capability.label}</h2><p>{capability.value}</p></div>)}
        </section>

        <section id="work" className="section">
          <div className="section-head"><div><p className="eyebrow">Selected work</p><h2>Systems with real operational context.</h2></div><a className="text-link" href={profile.github} target="_blank" rel="noreferrer">GitHub portfolio <Arrow /></a></div>
          <div className="project-grid">{projects.map((project, index) => <article className="project" key={project.name}><span className="project-number">0{index + 1}</span><p className="project-kind">{project.kind}</p><h3>{project.name}</h3><p className="project-description">{project.description}</p><div className="tags">{project.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></article>)}</div>
        </section>

        <section className="twin-grid"><div className="twin-copy"><p className="eyebrow">Portfolio Q&A</p><h2>A grounded conversation, not a generic chatbot.</h2><p>The Twin answers in my professional voice using a tightly scoped, fact-based profile. It is designed to discuss experience, engineering methods, and published project work.</p><div className="guardrail"><span>01</span><p>Server-side key handling, input limits, rate limiting, and a separate safety-model pass are built into the interface.</p></div></div><DigitalTwin /></section>

        <section id="experience" className="section experience-section"><div className="section-head"><div><p className="eyebrow">Career timeline</p><h2>Enterprise systems, evolving scope.</h2></div></div><div className="timeline">{experience.map((item) => <article key={`${item.period}-${item.company}`}><time>{item.period}</time><div><h3>{item.role}</h3><p className="company">{item.company}</p><p>{item.note}</p></div></article>)}</div></section>

        <footer><div><span className="wordmark"><span>AS</span> Abhishek Suman</span><p>Senior Network Engineer & GenAI/LLM Engineering Specialist</p></div><div className="footer-links"><a href={profile.linkedin} target="_blank" rel="noreferrer">LinkedIn <Arrow /></a><a href={profile.github} target="_blank" rel="noreferrer">GitHub <Arrow /></a><a href={`mailto:${profile.email}`}>Email <Arrow /></a></div></footer>
      </div>
    </main>
  );
}
