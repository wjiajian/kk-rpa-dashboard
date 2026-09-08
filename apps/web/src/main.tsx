import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider, App as AntApp } from "antd";
import zhCN from "antd/locale/zh_CN";
import "dayjs/locale/zh-cn";
import dayjs from "dayjs";
import App from "./App";
import "./styles.css";
dayjs.locale("zh-cn");
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#ff4d55",
          colorPrimaryHover: "#ff7076",
          colorPrimaryActive: "#e83d46",
          colorLink: "#3276ff",
          colorLinkHover: "#245bdb",
          colorTextLightSolid: "#ffffff",
          colorBgLayout: "#f5f6fa",
          colorBgContainer: "#ffffff",
          colorBgElevated: "#ffffff",
          colorInfo: "#3276ff",
          controlItemBgActive: "#edf3ff",
          colorText: "#242833",
          colorTextSecondary: "#8b92a3",
          colorBorder: "#dcdfe6",
          borderRadius: 7,
          fontFamily:
            '"PingFang SC", "Microsoft YaHei", -apple-system, sans-serif',
          fontSize: 14,
          controlHeight: 38,
        },
        components: {
          Switch: { colorPrimary: "#3276ff", colorPrimaryHover: "#528cff" },
          Input: { activeBorderColor: "#3276ff", hoverBorderColor: "#6e9fff" },
          Select: { activeBorderColor: "#3276ff", hoverBorderColor: "#6e9fff" },
          Table: {
            headerBg: "#f6f7fc",
            headerColor: "#515b70",
            rowHoverBg: "#fafbff",
            cellPaddingBlock: 17,
          },
          Button: { primaryShadow: "none", primaryColor: "#ffffff" },
          Tag: { defaultBg: "#f3f5fa" },
        },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);
