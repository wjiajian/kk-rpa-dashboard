import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider, App as AntApp } from "antd";
import zhCN from "antd/locale/zh_CN";
import "dayjs/locale/zh-cn";
import dayjs from "dayjs";
import { StoreProvider } from "./mock/store";
import App from "./App";
import "./styles.css";
dayjs.locale("zh-cn");
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#a8ce98",
          colorPrimaryHover: "#b9d9aa",
          colorPrimaryActive: "#91ba80",
          colorLink: "#477044",
          colorLinkHover: "#345b32",
          colorTextLightSolid: "#294329",
          colorBgLayout: "#f4f3ed",
          colorBgContainer: "#fffef8",
          colorBgElevated: "#fffef8",
          colorInfo: "#769866",
          controlItemBgActive: "#e7f0dc",
          colorText: "#303d30",
          colorTextSecondary: "#798471",
          colorBorder: "#dce2d1",
          borderRadius: 7,
          fontFamily:
            '"PingFang SC", "Microsoft YaHei", -apple-system, sans-serif',
          fontSize: 13,
          controlHeight: 36,
        },
        components: {
          Table: {
            headerBg: "#f3f5e9",
            headerColor: "#74816a",
            rowHoverBg: "#f0f5e7",
            cellPaddingBlock: 17,
          },
          Button: { primaryShadow: "none", primaryColor: "#294329" },
          Tag: { defaultBg: "#edf1e4" },
        },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <StoreProvider>
            <App />
          </StoreProvider>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);
