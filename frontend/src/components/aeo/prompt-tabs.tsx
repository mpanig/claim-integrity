import { SectionTabs } from "@/components/aeo/section-tabs";

export function PromptTabs() {
  return (
    <SectionTabs
      label="Prompt sections"
      tabs={[
        { href: "/aeo/prompts", label: "Library" },
        { href: "/aeo/prompts/plan", label: "Test plans & runs" },
      ]}
    />
  );
}
