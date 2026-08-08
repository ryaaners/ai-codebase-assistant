import { Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Workspace from "./pages/Workspace";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/repos/:repoId" element={<Workspace />} />
    </Routes>
  );
}
