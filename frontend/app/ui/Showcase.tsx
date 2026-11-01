"use client";
import { useState } from "react";
import {
  AttentionCard,
  Avatar,
  Badge,
  Button,
  Card,
  CaseCard,
  Chip,
  ListRow,
  PageHeader,
  Skeleton,
  StatTile,
  Tabs,
} from "./primitives";
import ThemeToggle from "./ThemeToggle";
import MiniCalendar from "./MiniCalendar";
export default function Showcase() {
  const [tab, setTab] = useState("active");
  return (
    <div className="hx-showcase">
      <PageHeader
        title="Homexo UI component review"
        subtitle="Shared production components · light and dark themes"
        actions={<ThemeToggle />}
      />
      {(["light", "dark"] as const).map((theme) => (
        <section data-theme={theme} className="hx-showcase-theme" key={theme}>
          <h2>{theme} theme</h2>
          <div className="hx-stat-grid">
            <StatTile
              tone="violet"
              icon="case"
              label="Open requests"
              value={2}
            />
            <StatTile
              tone="amber"
              icon="upload"
              label="Documents needed"
              value={1}
            />
            <StatTile
              tone="blue"
              icon="video"
              label="Next consultation"
              value="4:00 pm"
            />
            <StatTile
              tone="green"
              icon="check"
              label="Reports ready"
              value={1}
            />
          </div>
          <div className="hx-dashboard-grid">
            <div className="hx-dashboard-rail">
              <Card title="Buttons, badges and chips" icon="spark">
                <div className="hx-page-actions">
                  <Button variant="primary">Primary</Button>
                  <Button>Default</Button>
                  <Button variant="dark">Dark</Button>
                  <Button disabled>Disabled</Button>
                  <Chip selected>Selected</Chip>
                </div>
                <p>
                  {(
                    ["green", "amber", "red", "blue", "violet", "gray"] as const
                  ).map((tone) => (
                    <Badge key={tone} tone={tone}>
                      {tone}
                    </Badge>
                  ))}
                </p>
              </Card>
              <Card title="Case card">
                <Tabs
                  label={`${theme} sample tabs`}
                  value={tab}
                  onChange={setTab}
                  items={[
                    { id: "active", label: "Active" },
                    { id: "completed", label: "Completed" },
                  ]}
                />
                <CaseCard
                  title="Example property review"
                  subtitle="Component example · no real case"
                  stage="Lawyer review"
                  progress={0.65}
                  badge={{ tone: "amber", label: "Waiting" }}
                  actions={<Button size="sm">Documents</Button>}
                />
              </Card>
              <AttentionCard
                title="Upload the sale deed"
                meta="Example attention card"
                featured
                badge={{ tone: "amber", label: "Waiting" }}
              />
              <Skeleton height={60} />
            </div>
            <Card title="List rows and calendar" icon="cal">
              <ListRow
                leading={<Avatar initials="AR" />}
                title="Example advocate"
                meta="Component sample"
                trailing={<Badge tone="blue">Scheduled</Badge>}
              />
              <MiniCalendar marked={new Set()} onSelect={() => {}} />
            </Card>
          </div>
        </section>
      ))}
    </div>
  );
}
