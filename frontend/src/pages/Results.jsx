import { useState, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import bgImage from '../assets/background.jpg'

export default function Results() {
	// State for API response and loading status
	const [searchParams] = useSearchParams();
	const [results, setResults] = useState([]);
	const [seasonalContext, setSeasonalContext] = useState(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState(null);
	// Track which gift is currently being looked at
	const [currIndex, setCurrIndex] = useState(0);
	const [imgLoading, setImgLoading] = useState(true);

	// Reset the loader when navigating
	useEffect(() => {
		setImgLoading(true);
	}, [currIndex]);

	const SEASON_STYLES = {
		christmas:      { emoji: '🎄', color: '#e65100', bg: 'linear-gradient(135deg, #fff8e1, #ffe0b2)', border: '#ffcc80' },
		valentines:     { emoji: '❤️',  color: '#c62828', bg: 'linear-gradient(135deg, #fce4ec, #f8bbd0)', border: '#f48fb1' },
		mothers_day:    { emoji: '💐', color: '#6a1b9a', bg: 'linear-gradient(135deg, #f3e5f5, #e1bee7)', border: '#ce93d8' },
		fathers_day:    { emoji: '👔', color: '#1565c0', bg: 'linear-gradient(135deg, #e3f2fd, #bbdefb)', border: '#90caf9' },
		halloween:      { emoji: '🎃', color: '#e65100', bg: 'linear-gradient(135deg, #fff3e0, #ffe0b2)', border: '#ffb74d' },
		back_to_school: { emoji: '🎒', color: '#2e7d32', bg: 'linear-gradient(135deg, #e8f5e9, #c8e6c9)', border: '#a5d6a7' },
	};
	// Reads URL then performs fetch request
	useEffect(() => {
		const fetchResults = async () => {
			setLoading(true);
			try {
				// Fetch results using the current URL's search params
				const response = await fetch(`/search?${searchParams.toString()}`);

				if (!response.ok) throw new Error('Failed to fetch recommendations');

				const data = await response.json();

				// We access the 'gifts' key we defined in our FastAPI return statement
				setResults(data.gifts || []);
				setSeasonalContext(data.meta, null)
			} catch (error) {
				setError("Error connecting to backend: " + error.message);
			} finally {
				setLoading(false);
			}
		};
		fetchResults();
	}, [searchParams]); // Re-run when search params change

	// Navigation logic
	const handleNext = () => {
		if (currIndex < results.length - 1) setCurrIndex(currIndex + 1);
	}

	const handlePrev = () => {
		if (currIndex > 0) setCurrIndex(currIndex - 1);
	}

	// Add this simple effect to reset the loader when navigating

	if (loading) return <div style={{ textAlign: 'center', padding: '50px' }}>Finding the perfect gift...</div>;
	if (error) return <div style={{ color: 'red', textAlign: 'center' }}>Error: {error}</div>;
	if (results.length === 0) return <div style={{ textAlign: 'center' }}>No results found. <Link to="/">Try again</Link></div>;

	const currGift = results[currIndex];

	return (
		// Displays list of results as cards that user can click through
		<div style={{ 
			display: 'flex', 
			flexDirection: 'column', 
			alignItems: 'center', 
			justifyContent: 'center',
			minHeight: '100vh',
			padding: '20px',
			backgroundImage: `url(${bgImage})`,
			backgroundSize: 'cover',
			backgroundPosition: 'center',
			backgroundRepeat: 'no-repeat',
			backgroundAttachment: 'fixed'
		  }}>
			<Link to="/search" style={{ marginBottom: '20px', textDecoration: 'none', color: '#fff' }}>← Search Again</Link>
	  
			{/* Progress Indicator */}
			<p style={{ fontWeight: 'bold', color: '#fff' }}>Gift {currIndex + 1} of {results.length}</p>
	  
			<div style={{ 
			  display: 'flex', 
			  alignItems: 'center', 
			  gap: '20px', 
			  width: '100%', 
			  maxWidth: '900px' 
			}}>
			  {/* Left Button */}
			  <button 
				onClick={handlePrev} 
				disabled={currIndex === 0}
				style={navButtonStyle}
			  > 
				❮ 
			  </button>
	  
			  {/* Page-Wide Card */}
			  <div style={{ 
				flex: 1, 
				background: 'white', 
				padding: '40px', 
				borderRadius: '20px', 
				boxShadow: '0 10px 25px rgba(0,0,0,0.1)',
				textAlign: 'center'
			  }}>
				<h2 style={{ fontSize: '2rem', marginBottom: '10px' }}>{currGift.name}</h2>

				{/* Image */}
				<div style={{ 
					position: 'relative', 
					height: '300px',
					display: 'flex',
					justifyContent: 'center', 
					alignItems: 'center',
					}}>
					{/* Show this while imgLoading is true */}
					{imgLoading && <div style={{ textAlign: 'center' }}>Loading image...</div>}
					
					<img 
					src={`http://localhost:8000/proxy-image?product_url=${encodeURIComponent(currGift.url)}`}
					alt={currGift.name}
					onLoad={() => setImgLoading(false)} 
					style={{ 
						display: imgLoading ? 'none' : 'block', 
						maxWidth: '100%', 
						maxHeight: '100%' 
					}}
					onError={() => setImgLoading(false)} // Stop loading even if it fails
					/>
				</div>
				
				<p style={{ fontSize: '1.5rem', color: '#28a745', fontWeight: 'bold' }}>
				  ${currGift.price.toFixed(2)}
				</p>
				<p style={{ color: '#666', marginBottom: '20px' }}>Source: {currGift.source.toUpperCase()}</p>
				
				<div style={{ background: '#f8f9fa', padding: '15px', borderRadius: '10px', marginBottom: '30px' }}>
				  <strong>Why it matches:</strong> {currGift.matches.join(', ')}
				  {seasonalContext && seasonalContext.implicit_context !== "none" && (() => {
					const s = SEASON_STYLES[seasonalContext.implicit_context] || SEASON_STYLES.christmas;
					return (
						<div style={{
							background: s.bg,
							border: `1px solid ${s.border}`,
							borderRadius: '8px',
							padding: '8px 14px',
							display: 'flex',
							alignItems: 'center',
							gap: '8px',
							fontSize: '0.85rem',
							color: s.color,
							width: '50%',
							boxSizing: 'border-box',
							margin: '0 auto 16px auto'
						}}>
							<span style={{ fontSize: '1.1rem' }}>{s.emoji}</span>
							<span>
								Trending for <strong>{seasonalContext.implicit_context.replace(/_/g, ' ')}</strong>
								<br />
								<em style={{ fontSize: '0.78rem' }}> {seasonalContext.implicit_terms_used.join(', ')}</em>
							</span>
						</div>
					);
				})()}
				</div>
	
				<a 
				  href={currGift.url} 
				  target="_blank" 
				  rel="noreferrer" 
				  style={buyButtonStyle}
				>
				  View Product Website
				</a>
			  </div>
	  
			  {/* Right Button */}
			  <button 
				onClick={handleNext} 
				disabled={currIndex === results.length - 1}
				style={navButtonStyle}
			  > 
				❯ 
			  </button>
			</div>
		</div>
	);
}

// Simple Styles
const navButtonStyle = {
	fontSize: '2rem',
	background: 'white',
	border: '1px solid #ddd',
	borderRadius: '50%',
	width: '60px',
	height: '60px',
	cursor: 'pointer',
	display: 'flex',
	alignItems: 'center',
	justifyContent: 'center',
	boxShadow: '0 4px 6px rgba(0,0,0,0.05)',
	opacity: (props) => props.disabled ? 0.3 : 1
  };
  
  const buyButtonStyle = {
	display: 'inline-block',
	backgroundColor: '#e3242b',
	color: 'white',
	padding: '15px 30px',
	borderRadius: '30px',
	textDecoration: 'none',
	fontWeight: 'bold',
	fontSize: '1.1rem'
  };