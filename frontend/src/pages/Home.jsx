import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Home() {
	// Takes form inputs to build query params for results page
	const [formData, setFormData] = useState({
		recipient: '',
		minPrice: null,
		maxPrice: null,
		query: ''
	});
	const navigate = useNavigate();

	// Pushes user's choices into the URL as query params
	const handleSearch = (e) => {
		e.preventDefault();
		// Build query params (omit empty values so backend gets clean inputs)
		const params = new URLSearchParams();
		if (formData.recipient) params.set('recipient', formData.recipient);
		if (formData.query) params.set('q', formData.query);
		if (formData.minPrice !== null && formData.minPrice !== '' && !Number.isNaN(Number(formData.minPrice))) {
		params.set('min_price', String(formData.minPrice));
		}
		if (formData.maxPrice !== null && formData.maxPrice !== '' && !Number.isNaN(Number(formData.maxPrice))) {
		params.set('max_price', String(formData.maxPrice));
		}

		// Navigate to the results page with query params
		navigate(`/results?${params.toString()}`);
	};

	return (
		<div style={{ 
			display: 'flex',
			flexDirection: 'column',
			alignItems: 'center',		// centers horizontally
			justifyContent: 'center',	// centers vertically
			minHeight: '100vh',		// sets height to full screen
			width: '100vw',
			padding: '20px', 
			fontFamily: 'system-ui',
			boxSizing: 'border-box',
		  }}>
			<header style={{ textAlign: 'center', marginBottom: '40px' }}>
			  <h1>Personalized Gift Recommender for Every Occasion</h1>
			</header>
	  
			{/* --- Search Form --- */}
			<form onSubmit={handleSearch} style={{
			  width: '100%',
			  maxWidth: '500px', 
			  display: 'grid', 
			  gap: '20px', 
			  background: '#f8f9fa', 
			  padding: '20px', 
			  borderRadius: '12px',
			  boxShadow: '0 4px 6px rgba(0,0,0,0.1)' // Optional: adds a nice lift 
			}}>
			  <div>
				<label style={{ display: 'block', fontWeight: 'bold' }}>Who is the recipient?</label>
				<select 
				  value={formData.recipient}
				  onChange={(e) => setFormData({...formData, recipient: e.target.value})}
				  style={{ width: '100%', padding: '10px', marginTop: '5px' }}
				>
				  <option value = "">Select a recipient...</option>
				  <option value="mom">Mom</option>
				  <option value="dad">Dad</option>
				  <option value="friend">Friend</option>
				  <option value="colleague">Colleague</option>
				</select>
			  </div>
	  
			  <div style={{ display: 'flex', gap: '20px' }}>
				<div style={{ flex: 1 }}>
				  <label style={{ display: 'block', fontWeight: 'bold' }}>Min Price ($)</label>
				  <input 
					type="number" 
					placeholder="Min e.g. 10"
					value={formData.minPrice}
					onChange={(e) => setFormData({...formData, minPrice: e.target.value})}
					style={{ width: '95%', padding: '10px' }} 
				  />
				</div>
				<div style={{ flex: 1 }}>
				  <label style={{ display: 'block', fontWeight: 'bold' }}>Max Price ($)</label>
				  <input 
					type="number" 
					placeholder="Max e.g. 1000"
					value={formData.maxPrice}
					onChange={(e) => setFormData({...formData, maxPrice: e.target.value})}
					style={{ width: '95%', padding: '10px' }} 
				  />
				</div>
			  </div>
	  
			  <div>
				<label style={{ display: 'block', fontWeight: 'bold' }}>What are they interested in?</label>
				<input 
				  type="text" 
				  placeholder="e.g. video games, cooking, gardening"
				  value={formData.query}
				  onChange={(e) => setFormData({...formData, query: e.target.value})}
				  style={{ width: '95%', padding: '10px', marginTop: '5px' }}
				/>
			  </div>
	  
			  <button 
				type="submit" 
				style={{ 
				  backgroundColor: '#007bff', color: 'white', padding: '12px', 
				  border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' 
				}}
			  >
				Find Perfect Gift
			  </button>
			</form>
		</div>
	);
}