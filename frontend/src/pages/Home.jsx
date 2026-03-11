import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Home() {
	// Takes form inputs to build query params for results page
	const [formData, setFormData] = useState({
		recipient: '',
		minPrice: null,
		maxPrice: null,
		interests: [], // Use an array to store multiple interests
		otherInterest: '' // New field for user to input custom interest
	});
	const navigate = useNavigate();
	const categories = ["Video Games", "Cooking", "Gardening", "Tech", "Fitness", "Reading", "Other"]; // Predefined categories for user to choose from

	// Pushes user's choices into the URL as query params
	const handleSearch = (e) => {
		e.preventDefault();
		// Build query params (omit empty values so backend gets clean inputs)
		const params = new URLSearchParams();
		if (formData.recipient) params.set('recipient', formData.recipient);
		
		// Handle interests, including the "Other" option with custom text
		let finalInterests = [...formData.interests];
		if (finalInterests.includes("Other")) {
			// Remove the word "Other"
			finalInterests = finalInterests.filter(i => i !== "Other");
			// Add the custom text if it's not empty
			if (formData.otherInterest.trim() !== "") {
				finalInterests.push(formData.otherInterest.trim());
			}
		}
		if (finalInterests.length > 0) {
			params.set('q', finalInterests.join(','));
		}

		if (formData.minPrice !== null && formData.minPrice !== '' && !Number.isNaN(Number(formData.minPrice))) {
		params.set('min_price', String(formData.minPrice));
		}
		if (formData.maxPrice !== null && formData.maxPrice !== '' && !Number.isNaN(Number(formData.maxPrice))) {
		params.set('max_price', String(formData.maxPrice));
		}

		// Navigate to the results page with query params
		navigate(`/results?${params.toString()}`);
	};

	const handleSelectInterest = (interest) => {
		const isSelected = formData.interests.includes(interest);
		const newInterest = isSelected
			? formData.interests.filter((i) => i !== interest) // Remove if already selected
			: [...formData.interests, interest]; // Add if not selected

		setFormData({
			...formData,
			interests: newInterest,
			otherInterest: interest === "Other" && isSelected ? '' : formData.otherInterest // Clear otherInterest if "Other" is deselected
		});
	};

	return (
		<div style={{ 
			display: 'flex',
			flexDirection: 'column',
			alignItems: 'center',		// centers horizontally
			//justifyContent: 'center',	// centers vertically
			minHeight: '100vh',		// sets height to full screen
			width: '100vw',
			padding: '20px', 
			fontFamily: 'system-ui',
			boxSizing: 'border-box',
		  }}>
			<header style={{ textAlign: 'center', marginBottom: '10px' , marginTop: '5px'}}>
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
				<label style={{ display: 'block', fontWeight: 'bold', marginBottom: '10px' }}>
					What are they interested in?
				</label>
				{/* Interest buttons in a responsive grid */}
				<div style={{
					display: 'grid',
					gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
					gap: '8px'
				}}>
					{ categories.map((cat) => {
						const isSelected = formData.interests.includes(cat);
						return (
							<button
								key={cat}
								type="button"
								onClick={() => handleSelectInterest(cat)}
								style={{
									padding: '8px',
									borderRadius: '6px',
									border: isSelected ? '2px solid #007bff' : '1px solid #ccc',
									backgroundColor: isSelected ? '#e7f3ff' : '#fff',
									cursor: 'pointer',
									fontSize: '14px'
								}}
							>{cat == "Other" && isSelected ? "Other" : cat}
							</button>
						);
					})}
				</div>
				
				{/* Conditional "Other" Input */}
				{formData.interests.includes("Other") && (
					<div style={{ marginTop: '10px', animation: 'fadeIn 0.3s' }}>
						<input 
							type="text" 
							placeholder="Type custom interest..."
							value={formData.otherInterest}
							onChange={(e) => setFormData({...formData, otherInterest: e.target.value})}
							style={{ 
							width: '100%', 
							padding: '10px', 
							borderRadius: '6px',
							border: '1px solid #ccc',
							boxSizing: 'border-box'
						}}
						autoFocus
					/>
				</div>
			)}
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