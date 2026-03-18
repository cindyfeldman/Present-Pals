import React from 'react';
import {Link} from 'react-router-dom';
import './Home.css';
import Bow from './Bow';

const Home = () => {
	return (
	  <div className="home-container">
		<div className="cross-vertical" />
		<div className="cross-horizontal" />

		{/* Bow and Button Overlay */}
		<div className="bow-action-area">
			<Bow className="bow-svg" />
			<Link to="/search" className="start-button">
				Begin Gift Search
			</Link>
		</div>
	  </div>
	);
  };
  
  export default Home;