/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import type { ReactNode } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useSearchParams } from "react-router";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import {
  Menu,
  MenuContent,
  MenuGroup,
  MenuItem,
  MenuLabel,
  MenuSeparator,
  MenuTrigger,
} from "@makeplane/propel/components/menu";
import { Shortcut } from "@makeplane/propel/components/shortcut";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import {
  AddOutline,
  HomeOutline,
  InboxOutline,
  MembersOutline,
  ProjectsOutline,
  SearchOutline,
  SettingsOutline,
} from "@makeplane/propel/icons";
import { setToast } from "@plane/blocks/toast";
import { cn } from "@plane/utils";
import { SidebarNavItem } from "@/components/sidebar/sidebar-navigation";
import { RadarMockupCaptureDialog } from "./capture-dialog";
import { RadarMockupItemDrawer } from "./item-drawer";
import type { TScenario } from "./mockup.store";
import { RadarMockupProvider, useRadarMockup } from "./provider";
import { CloseDayDialog, OpenDayDialog } from "./rituals";
import { useMockupBase } from "./ui";

type TIcon = React.ComponentProps<typeof Icon>["icon"];

function NavLink({
  href,
  icon,
  label,
  active,
  count,
}: {
  href: string;
  icon: TIcon;
  label: string;
  active: boolean;
  count?: number;
}) {
  return (
    <Link href={href}>
      <SidebarNavItem isActive={active}>
        <span className="flex items-center gap-1.5 py-[1px] text-13 leading-5 font-medium">
          <Icon icon={icon} />
          {label}
        </span>
        {!!count && <span className="text-12 font-medium text-tertiary tabular-nums">{count}</span>}
      </SidebarNavItem>
    </Link>
  );
}

const outOfScope = (what: string) =>
  setToast({ type: "info", title: `${what} fica para depois`, message: "Fora do escopo destes mockups." });

/**
 * Settings. The first group is the product's (only a placeholder here); the second is demonstration only:
 * it changes the data, the clock and the scenario so the screens can be shown in every condition. None of it
 * exists in the product.
 */
const SettingsMenu = observer(function SettingsMenu({ side }: { side: "top" | "bottom" }) {
  const store = useRadarMockup();
  const base = useMockupBase();
  const router = useRouter();
  const scenario = store.demo.scenario;
  const pick = (value: TScenario, label: string, description: string) => (
    <MenuItem
      key={value}
      label={`${label}${scenario === value ? " · ativo" : ""}`}
      description={description}
      onClick={() => store.setScenario(value)}
    />
  );
  return (
    <MenuContent side={side} align="start">
      <MenuGroup>
        <MenuLabel>Configurações</MenuLabel>
        <MenuItem
          label="Outras configurações"
          description="Fora do escopo destes mockups"
          onClick={() => outOfScope("Configurações")}
        />
      </MenuGroup>
      <MenuSeparator />
      <MenuGroup>
        <MenuLabel>Apenas demonstração</MenuLabel>
        <MenuItem
          label="Demonstração · Primeiro uso, com vault"
          description="Esvazia Hoje; pessoas e projetos importados"
          onClick={() => {
            store.startFresh({ vault: true });
            router.push(`${base}/hoje/`);
          }}
        />
        <MenuItem
          label="Demonstração · Primeiro uso, sem vault"
          description="Esvazia tudo, inclusive pessoas e projetos"
          onClick={() => {
            store.startFresh({ vault: false });
            router.push(`${base}/hoje/`);
          }}
        />
        <MenuItem label="Demonstração · Restaurar dados de exemplo" onClick={store.resetSample} />
        {pick("loading", "Demonstração · Carregando", "As telas mostram a espera")}
        {pick("error", "Demonstração · Erro ao carregar", "Nada é mostrado, e isso é dito")}
        {pick("partial", "Demonstração · Dados incompletos", "Aguardando e Informar não carregam")}
        {pick("readonly", "Demonstração · Somente leitura", "Consultar sim, alterar não")}
        {scenario !== "normal" && pick("normal", "Demonstração · Voltar ao normal", "Dados completos")}
        <MenuItem
          label="Demonstração · Ir para o fim do dia"
          description={`Relógio em ${store.ritualTimes.fechar}`}
          onClick={() => store.advanceClock("evening")}
        />
        <MenuItem
          label="Demonstração · Ir para o dia seguinte"
          description={`Relógio em ${store.ritualTimes.abrir}`}
          onClick={() => store.advanceClock("nextDay")}
        />
        <MenuItem
          label={`Demonstração · Agente indisponível${store.demo.agentDown ? " · ativo" : ""}`}
          onClick={() => store.toggleDemo("agentDown")}
        />
        <MenuItem
          label={`Demonstração · Falha ao criar a próxima ação${store.demo.failMitigation ? " · ativo" : ""}`}
          description="Uma vez, ao aceitar uma proposta"
          onClick={() => store.toggleDemo("failMitigation")}
        />
      </MenuGroup>
    </MenuContent>
  );
});

/** On a phone the sidebar is gone: the four places and capture live in a bar at the bottom. */
const MobileNav = observer(function MobileNav({ active }: { active: (section: string) => boolean }) {
  const store = useRadarMockup();
  const base = useMockupBase();
  const items = [
    { section: "hoje", label: "Hoje", icon: HomeOutline, count: 0 },
    { section: "inbox", label: "Inbox", icon: InboxOutline, count: store.inboxCount },
    { section: "projetos", label: "Projetos", icon: ProjectsOutline, count: 0 },
    { section: "pessoas", label: "Pessoas", icon: MembersOutline, count: 0 },
  ];
  return (
    <nav
      aria-label="Navegação principal"
      className="flex shrink-0 items-stretch justify-around border-t border-subtle bg-surface-1 md:hidden"
    >
      {items.map((entry) => (
        <Link
          key={entry.section}
          href={`${base}/${entry.section}/`}
          aria-current={active(entry.section) ? "page" : undefined}
          className={cn(
            "relative flex min-h-12 flex-1 flex-col items-center justify-center gap-0.5 text-11 font-medium",
            active(entry.section) ? "text-accent-primary" : "text-secondary"
          )}
        >
          <Icon icon={entry.icon} />
          {entry.label}
          {entry.count > 0 && (
            <span className="absolute top-1 right-1/4 rounded-full bg-accent-primary px-1 text-10 text-white">
              {entry.count}
            </span>
          )}
        </Link>
      ))}
      <button
        type="button"
        aria-label="Capturar qualquer coisa"
        disabled={store.readOnly}
        onClick={() => store.setCaptureOpen(true)}
        className="flex min-h-12 flex-1 flex-col items-center justify-center gap-0.5 text-11 font-medium text-secondary disabled:opacity-50"
      >
        <Icon icon={AddOutline} />
        Novo
      </button>
    </nav>
  );
});

/** Says, above every screen, the condition the demonstration is in. */
const ScenarioBar = observer(function ScenarioBar() {
  const store = useRadarMockup();
  if (store.demo.scenario !== "readonly") return null;
  return (
    <div role="status" className="shrink-0 border-b border-subtle bg-layer-2 px-4 py-1.5 text-12 text-secondary">
      Somente leitura: você pode consultar, mas não alterar. As ações ficam desativadas.
    </div>
  );
});

const MockupFrame = observer(function MockupFrame({ children }: { children: ReactNode }) {
  const store = useRadarMockup();
  const base = useMockupBase();
  const pathname = usePathname();
  const [params, setParams] = useSearchParams();
  const urlItem = params.get("item");
  const active = (section: string) =>
    pathname.startsWith(`${base}/${section}`) || (section === "hoje" && pathname.replace(/\/$/, "") === base);

  // The open item lives in the address bar: a link, a reload and Back all bring it back. The URL is the
  // source of truth; the store only asks for changes through it.
  useEffect(() => {
    store.syncOpenItem(urlItem);
  }, [store, urlItem]);
  useEffect(() => {
    store.bindUrl((id) =>
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (id) next.set("item", id);
          else next.delete("item");
          return next;
        },
        { replace: id === null }
      )
    );
    return () => store.bindUrl(null);
  }, [store, setParams]);

  // "C" captures from anywhere, like Plane's own shortcuts; ignored while typing.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        target?.closest("input, textarea, [contenteditable='true']")
      )
        return;
      if (event.key.toLowerCase() === "c") {
        event.preventDefault();
        store.setCaptureOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [store]);

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden rounded-lg border border-subtle">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-subtle px-4 py-2 md:hidden">
        <span className="flex items-center gap-2 text-16 font-medium text-primary">
          RADAR <Badge variant="purple" size="sm" label="Mockup" />
        </span>
        <Menu>
          <MenuTrigger
            render={
              <IconButton variant="ghost" size="md" aria-label="Configurações" icon={<Icon icon={SettingsOutline} />} />
            }
          />
          <SettingsMenu side="bottom" />
        </Menu>
      </div>
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        <aside
          className="hidden h-full w-[240px] shrink-0 flex-col border-r border-subtle bg-surface-1 md:flex"
          aria-label="RADAR"
        >
          <div className="flex items-center justify-between gap-2 px-5 pt-3 pb-2">
            <span className="text-16 font-medium text-primary">RADAR</span>
            <Badge variant="purple" size="sm" label="Mockup" />
          </div>
          <div className="px-3 pb-3">
            <Tooltip label="Capturar qualquer coisa" shortcut="C">
              <Button
                variant="secondary"
                size="md"
                stretch="full"
                icon={<Icon icon={AddOutline} />}
                label="Novo"
                disabled={store.readOnly}
                onClick={() => store.setCaptureOpen(true)}
              />
            </Tooltip>
          </div>
          <nav className="flex flex-col gap-0.5 px-3" aria-label="Navegação principal">
            <NavLink href={`${base}/hoje/`} icon={HomeOutline} label="Hoje" active={active("hoje")} />
            <NavLink
              href={`${base}/inbox/`}
              icon={InboxOutline}
              label="Inbox"
              active={active("inbox")}
              count={store.inboxCount}
            />
            <NavLink href={`${base}/projetos/`} icon={ProjectsOutline} label="Projetos" active={active("projetos")} />
            <NavLink href={`${base}/pessoas/`} icon={MembersOutline} label="Pessoas" active={active("pessoas")} />
          </nav>
          <div className="flex-1" />
          <div className="flex flex-col gap-0.5 border-t border-subtle px-3 py-3">
            <button type="button" className="text-left" onClick={() => outOfScope("A busca global")}>
              <SidebarNavItem>
                <span className="flex items-center gap-1.5 py-[1px] text-13 leading-5 font-medium">
                  <Icon icon={SearchOutline} />
                  Buscar
                </span>
                <Shortcut keys="⌘K" />
              </SidebarNavItem>
            </button>
            <Menu>
              <MenuTrigger
                render={
                  <button type="button" className="text-left">
                    <SidebarNavItem>
                      <span className="flex items-center gap-1.5 py-[1px] text-13 leading-5 font-medium">
                        <Icon icon={SettingsOutline} />
                        Configurações
                      </span>
                    </SidebarNavItem>
                  </button>
                }
              />
              <SettingsMenu side="top" />
            </Menu>
          </div>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <ScenarioBar />
          {/* A new day remounts the screens, so every relative date ("amanhã", "há 2 dias") is read again. */}
          <main key={store.today} className="relative flex min-h-0 w-full flex-1 flex-col overflow-y-auto bg-surface-1">
            {children}
          </main>
        </div>
      </div>
      <MobileNav active={active} />
      <RadarMockupItemDrawer />
      <RadarMockupCaptureDialog />
      <OpenDayDialog />
      <CloseDayDialog />
    </div>
  );
});

/**
 * Shell for the RADAR_UX_VIEW mockups: Hoje, Inbox, Projetos and Pessoas on the left (at the bottom on a
 * phone), everything else reachable from search or settings. Mock data only; no RADAR store, API or agent.
 */
export function RadarMockupShell({ children }: { children: ReactNode }) {
  return (
    <RadarMockupProvider>
      <MockupFrame>{children}</MockupFrame>
    </RadarMockupProvider>
  );
}
