import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Results from './pages/Results'
// import reactLogo from './assets/react.svg'
// import viteLogo from '/vite.svg'
// import './App.css'

function App() {
  return (
	<BrowserRouter>
	  <Routes>
		<Route path="/" element={<Home />} />
		<Route path="/results" element={<Results />} />
	  </Routes>
	</BrowserRouter>
  );
}

export default App;