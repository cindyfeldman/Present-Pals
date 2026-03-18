import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Results from './pages/Results'
import Search from './pages/Search'
import './App.css'
// import reactLogo from './assets/react.svg'
// import viteLogo from '/vite.svg'


function App() {
  // Acts as a 'router' to switch between our Home and Results pages
  return (
	<BrowserRouter>
	  <Routes>
		<Route path="/" element={<Home />} />
		<Route path="/search" element={<Search />} />
		<Route path="/results" element={<Results />} />
	  </Routes>
	</BrowserRouter>
  );
}

export default App;