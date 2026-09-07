import { createContext, useContext, useState, type ReactNode } from "react";
import {
  applications as seedApps,
  tasks as seedTasks,
  runs as seedRuns,
  type Application,
  type Task,
  type Run,
} from "./data";
interface Store {
  apps: Application[];
  tasks: Task[];
  runs: Run[];
  member: boolean;
  setMember: (v: boolean) => void;
  saveTask: (t: Task) => void;
  setApps: React.Dispatch<React.SetStateAction<Application[]>>;
  setRuns: React.Dispatch<React.SetStateAction<Run[]>>;
  admins: string[];
  setAdmins: React.Dispatch<React.SetStateAction<string[]>>;
  retention: number;
  setRetention: (n: number) => void;
}
const Context = createContext<Store>(null!);
export function StoreProvider({ children }: { children: ReactNode }) {
  const [apps, setApps] = useState(seedApps);
  const [tasks, setTasks] = useState(seedTasks);
  const [runs, setRuns] = useState(seedRuns);
  const [member, setMember] = useState(false);
  const [admins, setAdmins] = useState(["邵健", "陈晓"]);
  const [retention, setRetention] = useState(30);
  return (
    <Context.Provider
      value={{
        apps,
        tasks,
        runs,
        member,
        setMember,
        setApps,
        setRuns,
        admins,
        setAdmins,
        retention,
        setRetention,
        saveTask: (t) =>
          setTasks((old) =>
            old.some((x) => x.id === t.id)
              ? old.map((x) => (x.id === t.id ? t : x))
              : [t, ...old],
          ),
      }}
    >
      {children}
    </Context.Provider>
  );
}
export const useStore = () => useContext(Context);
