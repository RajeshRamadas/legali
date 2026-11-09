"use client";

import { createContext, useContext, type HTMLAttributes } from "react";

const WithinMain = createContext(false);

// Pages can also render inside a workspace shell. Keep one main landmark in either case.
export default function MainContent({ children, ...props }: HTMLAttributes<HTMLElement>) {
  const nested = useContext(WithinMain);
  const Element = nested ? "div" : "main";
  return (
    <WithinMain.Provider value={true}>
      <Element {...props} {...(!nested ? { id: "main-content", tabIndex: -1 } : {})}>
        {children}
      </Element>
    </WithinMain.Provider>
  );
}
